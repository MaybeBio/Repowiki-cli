"""ZreadClient: RSC scraping + REST metadata + ask talk over httpx."""

from __future__ import annotations

import asyncio
import json
import ssl

import httpx

from repowiki.services.zread.flight import (
    WikiInfo,
    Page,
    parse_wiki_data,
    rewrite_callouts,
    strip_frontmatter,
)
from repowiki.shared.github import GithubError, fetch_github_head, split_repo
from repowiki.shared.retry import TRANSIENT_STATUS, backoff

BASE = "https://zread.ai"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
class ZreadError(Exception):
    """Base error for Zread."""


class ZreadConnectionError(ZreadError):
    """Failed to reach zread.ai."""


class ZreadNotFoundError(ZreadError):
    """Repo/page not indexed or not found on zread.ai."""


class ZreadChallengeError(ZreadError):
    """Cloudflare challenge or rate-limit (403/429/503)."""


def _split(repo: str) -> tuple[str, str]:
    owner, _, name = repo.partition("/")
    if not name:
        raise ValueError(f"invalid repo: {repo!r}")
    return owner, name


def _is_cert_error(exc: BaseException) -> bool:
    while exc is not None:
        if isinstance(exc, ssl.SSLCertVerificationError):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        for key in ("msg", "detail", "message", "error"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return resp.text.strip()[:500]


def _unwrap(resp: httpx.Response) -> object:
    try:
        result = resp.json()
    except json.JSONDecodeError as exc:
        raise ZreadError("invalid JSON response from Zread") from exc
    if not isinstance(result, dict) or result.get("code") != 0:
        msg = result.get("msg") if isinstance(result, dict) else "unknown"
        raise ZreadError(f"Zread API error: {msg}")
    return result.get("data")


class _SSEParser:
    """Incrementally parse the talk SSE stream.

    ``answer`` events carry incremental chunks — ``data.text`` is the answer and
    ``data.reasoning_content`` is the model's thinking trace (streamed first, then
    empty during the answer phase). ``round_finish`` carries the complete text,
    ``finish`` ends the stream. ``on_chunk`` / ``on_reasoning``, when given, are
    invoked with each ``answer`` chunk as it arrives.
    """

    def __init__(self, on_chunk=None, on_reasoning=None) -> None:
        self._on_chunk = on_chunk
        self._on_reasoning = on_reasoning
        self._event: str | None = None
        self._finished: list[str] = []
        self._chunks: list[str] = []
        self._reasoning: list[str] = []
        self._message_id = ""

    def feed(self, line: str) -> bool:
        """Consume one raw SSE line; return True when the stream is done."""
        line = line.strip()
        if not line:
            return False
        if line.startswith("event:"):
            self._event = line[6:].strip()
            if self._event == "finish":
                return True
            if self._event == "error":
                raise ZreadError("talk stream returned an error event")
        elif line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                return False
            if data.get("id"):
                self._message_id = data["id"]
            if self._event == "round_finish":
                self._finished.append(data.get("text", ""))
            elif self._event == "answer":
                reasoning = data.get("reasoning_content", "")
                if reasoning:
                    self._reasoning.append(reasoning)
                    if self._on_reasoning is not None:
                        self._on_reasoning(reasoning)
                text = data.get("text", "")
                self._chunks.append(text)
                if self._on_chunk is not None and text:
                    self._on_chunk(text)
        return False

    @property
    def text(self) -> str:
        return ("\n".join(self._finished) or "".join(self._chunks)).strip()

    @property
    def reasoning(self) -> str:
        return "".join(self._reasoning).strip()

    @property
    def message_id(self) -> str:
        return self._message_id


def _parse_sse_body(lines: list[str], on_chunk=None, on_reasoning=None) -> str:
    parser = _SSEParser(on_chunk, on_reasoning)
    for line in lines:
        if parser.feed(line):
            break
    return parser.text


class ZreadClient:
    """Stateless client; language/model/token are fixed per instance."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        lang: str = "en",
        model: str = "glm-5.1",
        token: str | None = None,
        retries: int = 5,
    ) -> None:
        self._transport = transport
        self._lang = lang
        self._model = model
        self._token = token
        self._retries = retries

    def _http(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout,
            verify=True,
            headers={"User-Agent": USER_AGENT},
            cookies={"X-Locale": self._lang},
            transport=self._transport,
        )

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"x-locale": self._lang}
        if extra:
            h.update(extra)
        return h

    async def _request(
        self,
        method: str,
        url: str,
        *,
        timeout: float,
        headers: dict | None = None,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> httpx.Response:
        async with self._http(timeout) as http:
            for attempt in range(1, self._retries + 1):
                try:
                    resp = await http.request(
                        method, url, headers=headers, params=params, json=json_body,
                    )
                except httpx.TransportError as exc:
                    message = f"Failed to connect to Zread: {exc}"
                    if _is_cert_error(exc):
                        message += (
                            " (TLS certificate verification failed; set SSL_CERT_FILE "
                            "to your CA bundle to trust a proxy/mirror)"
                        )
                    if attempt >= self._retries or _is_cert_error(exc):
                        raise ZreadConnectionError(message) from exc
                    await asyncio.sleep(backoff(attempt))
                    continue
                if resp.status_code == 429 and attempt < self._retries:
                    wait = backoff(attempt)
                    try:
                        wait = max(wait, float(resp.headers.get("Retry-After", "")))
                    except ValueError:
                        pass
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code in TRANSIENT_STATUS and attempt < self._retries:
                    await asyncio.sleep(backoff(attempt))
                    continue
                if resp.status_code in (403, 429, 503):
                    raise ZreadChallengeError(f"Zread returned HTTP {resp.status_code} (Cloudflare)")
                if resp.status_code == 404:
                    raise ZreadNotFoundError(f"Zread returned HTTP 404 for {url}")
                if resp.status_code in TRANSIENT_STATUS:
                    raise ZreadConnectionError(
                        f"Zread returned HTTP {resp.status_code} after {self._retries} attempts"
                    )
                if not resp.is_success:
                    detail = _error_detail(resp)
                    raise ZreadError(
                        f"Zread returned HTTP {resp.status_code} for {url}"
                        + (f": {detail}" if detail else "")
                    )
                return resp
        raise ZreadError(f"Zread request failed after {self._retries} attempts")

    async def repo_info(self, repo: str) -> dict:
        owner, name = _split(repo)
        resp = await self._request(
            "GET", f"{BASE}/api/v1/repo/github/{owner}/{name}",
            timeout=30.0, headers=self._headers(),
        )
        return _unwrap(resp) or {}

    async def search_repos(self, query: str) -> list:
        resp = await self._request(
            "GET", f"{BASE}/api/v1/repo", timeout=30.0,
            params={"q": query}, headers=self._headers(),
        )
        return _unwrap(resp) or []

    async def trending(self) -> list:
        resp = await self._request(
            "GET", f"{BASE}/api/v1/public/repo/trending",
            timeout=30.0, headers=self._headers(),
        )
        return _unwrap(resp) or []

    async def recommend(self, topic: str = "") -> dict:
        params = {"topic": topic} if topic else None
        resp = await self._request(
            "GET", f"{BASE}/api/v1/repo/recommend", timeout=30.0,
            params=params, headers=self._headers(),
        )
        return _unwrap(resp) or {}

    async def submit(self, repo: str) -> dict:
        if not self._token:
            raise ZreadError(
                "ZREAD_TOKEN is required for submit. Get it from zread.ai after login: "
                "run JSON.parse(localStorage.getItem('CGX_AUTH_STORAGE')).state.token in "
                "the DevTools console, then export ZREAD_TOKEN."
            )
        resp = await self._request(
            "POST", f"{BASE}/api/v1/public/repo/submit", timeout=30.0,
            # The endpoint 400s without notification_email; upstream sends this placeholder.
            json_body={"name_or_path": repo, "notification_email": "example@zread.ai"},
            headers=self._headers({"Authorization": f"Bearer {self._token}"}),
        )
        return _unwrap(resp) or {}

    async def search_wiki(self, repo: str, query: str) -> list:
        info = await self.repo_info(repo)
        wiki_id = str(info.get("wiki_id") or "")
        if not wiki_id:
            raise ZreadNotFoundError(f"no wiki_id for {repo}")
        resp = await self._request(
            "GET", f"{BASE}/api/v1/wiki/{wiki_id}/search", timeout=30.0,
            params={"q": query}, headers=self._headers(),
        )
        return _unwrap(resp) or []

    async def refresh(self, repo: str) -> dict:
        info = await self.repo_info(repo)
        repo_id = str(info.get("repo_id") or "")
        if not repo_id:
            raise ZreadNotFoundError(f"no repo_id for {repo}")
        await self._request(
            "POST", f"{BASE}/api/v1/repo/{repo_id}/refresh", timeout=30.0,
            headers=self._headers(),
        )
        return {"repo_id": repo_id, "ok": True}

    async def eta(self) -> dict:
        resp = await self._request(
            "GET", f"{BASE}/api/v1/repo/eta", timeout=30.0, headers=self._headers(),
        )
        return _unwrap(resp) or {}

    async def github_head(self, repo: str) -> dict:
        """Return the GitHub HEAD commit for a repo: ``{"sha": ..., "when": ...}``."""
        owner, name = split_repo(repo)
        try:
            async with httpx.AsyncClient(
                timeout=30.0, follow_redirects=True, transport=self._transport,
            ) as client:
                return await fetch_github_head(client, owner, name)
        except httpx.TransportError as exc:
            message = f"Failed to connect to GitHub: {exc}"
            if _is_cert_error(exc):
                message += (
                    " (TLS certificate verification failed; set SSL_CERT_FILE "
                    "to your CA bundle to trust a proxy/mirror)"
                )
            raise ZreadConnectionError(message) from exc
        except GithubError as exc:
            raise ZreadError(str(exc)) from exc

    async def read_file(
        self, repo_id: str, path: str,
        start: int | None = None, end: int | None = None,
    ) -> str:
        item = {"path": path}
        if start is not None:
            item["start_line"] = start
        if end is not None:
            item["end_line"] = end
        resp = await self._request(
            "POST", f"{BASE}/api/v1/repo/{repo_id}/files", timeout=30.0,
            json_body={"files": [item]}, headers=self._headers(),
        )
        files = _unwrap(resp)
        if not isinstance(files, list) or not files:
            raise ZreadNotFoundError(f"file not found: {path}")
        info = files[0]
        snippet = info.get("snippet")
        if isinstance(snippet, dict) and snippet.get("content") is not None:
            return snippet["content"]
        return info.get("content", "")

    async def outline(self, repo: str) -> tuple[WikiInfo, list[Page]]:
        wiki_id = await self._wiki_id(repo)
        resp = await self._request(
            "GET", f"{BASE}/api/v1/wiki/{wiki_id}", timeout=30.0, headers=self._headers(),
        )
        data = _unwrap(resp)
        if not isinstance(data, dict):
            raise ZreadNotFoundError(f"no wiki found for {repo}")
        wiki_info, pages = parse_wiki_data(data)
        if not pages:
            raise ZreadNotFoundError(f"no wiki found for {repo}")
        return wiki_info, pages

    async def page(self, repo: str, slug: str | None = None) -> str:
        wiki_id = await self._wiki_id(repo)
        if slug is None:
            _, pages = await self.outline(repo)
            if not pages:
                raise ZreadNotFoundError(f"no wiki pages for {repo}")
            slug = pages[0].slug
        resp = await self._request(
            "GET", f"{BASE}/api/v1/wiki/{wiki_id}/page/{slug}", timeout=30.0,
            headers=self._headers(),
        )
        data = _unwrap(resp)
        if not isinstance(data, dict):
            raise ZreadNotFoundError(f"no markdown found for {repo}/{slug}")
        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ZreadNotFoundError(f"no markdown found for {repo}/{slug}")
        return rewrite_callouts(strip_frontmatter(content))

    async def _wiki_id(self, repo: str) -> str:
        info = await self.repo_info(repo)
        wiki_id = str(info.get("wiki_id") or "")
        if not wiki_id:
            raise ZreadNotFoundError(f"no wiki_id for {repo}")
        return wiki_id

    async def ask(self, repo: str, question: str, on_chunk=None, on_reasoning=None) -> str:
        if not self._token:
            raise ZreadError(
                "ZREAD_TOKEN is required for ask. Get it from zread.ai after login: "
                "run JSON.parse(localStorage.getItem('CGX_AUTH_STORAGE')).state.token in "
                "the DevTools console, then export ZREAD_TOKEN."
            )
        talk = await self.start_talk(repo)
        return await talk.ask(question, on_chunk=on_chunk, on_reasoning=on_reasoning)

    async def start_talk(self, repo: str) -> "ZreadTalk":
        """Resolve a repo and open a new talk thread (``talk_id``)."""
        if not self._token:
            raise ZreadError(
                "ZREAD_TOKEN is required for ask. Get it from zread.ai after login: "
                "run JSON.parse(localStorage.getItem('CGX_AUTH_STORAGE')).state.token in "
                "the DevTools console, then export ZREAD_TOKEN."
            )
        info = await self.repo_info(repo)
        repo_id = str(info.get("repo_id") or "")
        wiki_id = str(info.get("wiki_id") or "")
        if not repo_id or not wiki_id:
            raise ZreadNotFoundError(f"{repo} is not indexed on zread.ai")
        _, pages = await self.outline(repo)
        if not pages:
            raise ZreadNotFoundError(f"{repo} has no wiki pages")
        talk_id = await self._create_talk()
        return ZreadTalk(self, repo_id, wiki_id, pages[0].page_id, talk_id)

    async def _create_talk(self) -> str:
        resp = await self._request(
            "POST", f"{BASE}/api/v1/talk", timeout=30.0,
            json_body={"query": " "},
            headers=self._headers({"Authorization": f"Bearer {self._token}"}),
        )
        data = _unwrap(resp) or {}
        talk_id = data.get("talk_id")
        if not talk_id:
            raise ZreadError("talk creation returned no talk_id")
        return talk_id

    async def _send_message(
        self, talk_id: str, question: str,
        wiki_id: str, page_id: str, repo_id: str,
        on_chunk=None, on_reasoning=None, parent_message_id: str = "",
    ) -> tuple[str, str]:
        url = f"{BASE}/api/v1/talk/{talk_id}/message"
        headers = self._headers({
            "Authorization": f"Bearer {self._token}",
            "Accept": "text/event-stream",
        })
        context = {"wiki": {"page_id": page_id, "wiki_id": wiki_id}}
        if repo_id:
            context["repo"] = {"repo_id": repo_id}
        body = {
            "parent_message_id": parent_message_id,
            "query": question,
            "context": context,
            "model": self._model,
        }
        for attempt in range(1, self._retries + 1):
            # Once chunks have reached the caller, a retry would replay them, so
            # a drop is only recoverable while nothing has been emitted yet.
            emitted = False

            def mark(callback, text):
                nonlocal emitted
                emitted = True
                if callback is not None:
                    callback(text)

            parser = _SSEParser(
                (lambda t: mark(on_chunk, t)) if on_chunk else None,
                (lambda t: mark(on_reasoning, t)) if on_reasoning else None,
            )
            retry_wait: float | None = None
            try:
                async with self._http(timeout=120.0) as http:
                    async with http.stream("POST", url, headers=headers, json=body) as resp:
                        if resp.status_code == 429 and attempt < self._retries:
                            wait = backoff(attempt)
                            try:
                                wait = max(wait, float(resp.headers.get("Retry-After", "")))
                            except ValueError:
                                pass
                            retry_wait = wait
                        elif resp.status_code in TRANSIENT_STATUS and attempt < self._retries:
                            retry_wait = backoff(attempt)
                        elif resp.status_code in (403, 429, 503):
                            raise ZreadChallengeError(
                                f"Zread returned HTTP {resp.status_code} (Cloudflare)"
                            )
                        elif resp.status_code == 404:
                            raise ZreadNotFoundError(f"talk not found: {talk_id}")
                        elif resp.status_code in TRANSIENT_STATUS:
                            raise ZreadConnectionError(
                                f"Zread returned HTTP {resp.status_code} "
                                f"after {self._retries} attempts"
                            )
                        elif not resp.is_success:
                            await resp.aread()
                            detail = _error_detail(resp)
                            raise ZreadError(
                                f"Zread returned HTTP {resp.status_code} for {url}"
                                + (f": {detail}" if detail else "")
                            )
                        else:
                            async for line in resp.aiter_lines():
                                if parser.feed(line):
                                    break
                            return parser.text, parser.message_id
            except httpx.TransportError as exc:
                message = f"Failed to connect to Zread: {exc}"
                if _is_cert_error(exc):
                    message += (
                        " (TLS certificate verification failed; set SSL_CERT_FILE "
                        "to your CA bundle to trust a proxy/mirror)"
                    )
                    raise ZreadConnectionError(message) from exc
                if emitted or attempt >= self._retries:
                    raise ZreadConnectionError(message) from exc
                retry_wait = backoff(attempt)
            if retry_wait is not None:
                await asyncio.sleep(retry_wait)
        raise ZreadConnectionError(
            f"Zread talk request failed after {self._retries} attempts"
        )


class ZreadTalk:
    """A single threaded conversation against one repo.

    Holds the ``talk_id`` and chains messages via ``parent_message_id`` (the id
    of the previous assistant message, captured from the SSE ``id`` field) so
    follow-up questions carry conversational memory.
    """

    def __init__(
        self, client: "ZreadClient", repo_id: str, wiki_id: str, page_id: str, talk_id: str
    ) -> None:
        self._client = client
        self._repo_id = repo_id
        self._wiki_id = wiki_id
        self._page_id = page_id
        self._talk_id = talk_id
        self._parent_message_id = ""

    async def ask(self, question: str, on_chunk=None, on_reasoning=None) -> str:
        answer, message_id = await self._client._send_message(
            self._talk_id, question, self._wiki_id, self._page_id, self._repo_id,
            on_chunk=on_chunk, on_reasoning=on_reasoning,
            parent_message_id=self._parent_message_id,
        )
        if message_id:
            self._parent_message_id = message_id
        return answer

"""ZreadClient: RSC scraping + REST metadata + ask talk over httpx."""

from __future__ import annotations

import asyncio
import json
import random
import ssl

import httpx

from repowiki.services.zread.flight import (
    WikiInfo,
    Page,
    extract_flight,
    extract_markdown,
    parse_wiki,
    rewrite_callouts,
    strip_frontmatter,
)

BASE = "https://zread.ai"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 528, 529}


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


def _backoff(attempt: int) -> float:
    return min(2 ** attempt + random.uniform(0, 1.5), 30.0)


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


def _parse_sse_body(lines: list[str]) -> str:
    event = None
    finished: list[str] = []
    chunks: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
            if event == "finish":
                break
            if event == "error":
                raise ZreadError("talk stream returned an error event")
        elif line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if event == "round_finish":
                finished.append(data.get("text", ""))
            elif event == "answer":
                chunks.append(data.get("text", ""))
    text = "\n".join(finished) or "".join(chunks)
    return text.strip()


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
                    await asyncio.sleep(_backoff(attempt))
                    continue
                if resp.status_code == 429 and attempt < self._retries:
                    wait = _backoff(attempt)
                    try:
                        wait = max(wait, float(resp.headers.get("Retry-After", "")))
                    except ValueError:
                        pass
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code in _TRANSIENT_STATUS and attempt < self._retries:
                    await asyncio.sleep(_backoff(attempt))
                    continue
                if resp.status_code in (403, 429, 503):
                    raise ZreadChallengeError(f"Zread returned HTTP {resp.status_code} (Cloudflare)")
                if resp.status_code == 404:
                    raise ZreadNotFoundError(f"Zread returned HTTP 404 for {url}")
                if resp.status_code in _TRANSIENT_STATUS:
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
        owner, name = _split(repo)
        resp = await self._request(
            "GET", f"{BASE}/{owner}/{name}", timeout=90.0, headers=self._headers(),
        )
        parsed = parse_wiki(extract_flight(resp.text))
        if parsed is None:
            raise ZreadNotFoundError(f"no wiki found for {repo}")
        return parsed

    async def page(self, repo: str, slug: str | None = None) -> str:
        owner, name = _split(repo)
        url = f"{BASE}/{owner}/{name}" + (f"/{slug}" if slug else "")
        for headers in (self._headers({"RSC": "1"}), self._headers()):
            resp = await self._request("GET", url, timeout=90.0, headers=headers)
            md = extract_markdown(extract_flight(resp.text), slug)
            if md:
                return rewrite_callouts(strip_frontmatter(md))
        raise ZreadNotFoundError(f"no markdown found for {repo}" + (f"/{slug}" if slug else ""))

    async def ask(self, repo: str, question: str) -> str:
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
        return await self._send_message(talk_id, question, wiki_id, pages[0].page_id, repo_id)

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
    ) -> str:
        url = f"{BASE}/api/v1/talk/{talk_id}/message"
        headers = self._headers({
            "Authorization": f"Bearer {self._token}",
            "Accept": "text/event-stream",
        })
        context = {"wiki": {"page_id": page_id, "wiki_id": wiki_id}}
        if repo_id:
            context["repo"] = {"repo_id": repo_id}
        body = {
            "parent_message_id": "",
            "query": question,
            "context": context,
            "model": self._model,
        }
        async with self._http(timeout=120.0) as http:
            async with http.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code in (403, 429, 503):
                    raise ZreadChallengeError(f"Zread returned HTTP {resp.status_code}")
                if resp.status_code == 404:
                    raise ZreadNotFoundError(f"talk not found: {talk_id}")
                if not resp.is_success:
                    await resp.aread()
                    detail = _error_detail(resp)
                    raise ZreadError(
                        f"Zread returned HTTP {resp.status_code} for {url}"
                        + (f": {detail}" if detail else "")
                    )
                lines = [line async for line in resp.aiter_lines()]
        return _parse_sse_body(lines)

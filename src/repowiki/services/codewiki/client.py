"""CodeWiki client: bootstrap + Google batchexecute RPC."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from repowiki.services.codewiki import boq
from repowiki.services.codewiki.wiki import Wiki, parse as parse_wiki

SITE = "https://codewiki.google"
ENDPOINT = f"{SITE}/_/BoqAngularSdlcAgentsUi/data/batchexecute"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
CACHE_TTL_SECS = 6 * 60 * 60

FALLBACK_BL = "boq_sdlc-agents-ui_20260504.02_p0"
FALLBACK_SID = "-8491411211174446345"

_WIZ_RE = re.compile(r"WIZ_global_data\s*=\s*(\{[\s\S]*?\});")


class CodeWikiError(Exception):
    """Base error for CodeWiki."""


class CodeWikiConnectionError(CodeWikiError):
    """Failed to reach codewiki.google."""


@dataclass
class _Bootstrap:
    bl: str
    sid: str
    fetched_at: float = 0.0


def extract_bootstrap(html: str) -> _Bootstrap:
    match = _WIZ_RE.search(html)
    if match is None:
        raise ValueError("WIZ_global_data not found in page HTML")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError("WIZ_global_data is not valid JSON") from exc
    bl = data.get("cfb2h")
    sid = data.get("FdrFJe")
    if not isinstance(bl, str):
        raise ValueError("missing cfb2h (build label) in WIZ_global_data")
    if not isinstance(sid, str):
        raise ValueError("missing FdrFJe (session id) in WIZ_global_data")
    return _Bootstrap(bl=bl, sid=sid, fetched_at=time.time())


def _cache_path() -> Path | None:
    if env := os.environ.get("CODEWIKI_CACHE_DIR"):
        return Path(env) / "bootstrap.json"
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base) / "codewiki" / "bootstrap.json"


def _read_cache(path: Path) -> _Bootstrap | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _Bootstrap(
            bl=data["bl"], sid=data["sid"], fetched_at=float(data.get("fetched_at", 0))
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(path: Path | None, bs: _Bootstrap) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"bl": bs.bl, "sid": bs.sid, "fetched_at": bs.fetched_at}),
            encoding="utf-8",
        )
    except OSError:
        pass


async def _fetch_bootstrap(http: httpx.AsyncClient) -> _Bootstrap:
    resp = await http.get(SITE)
    resp.raise_for_status()
    return extract_bootstrap(resp.text)


async def _load_bootstrap(http: httpx.AsyncClient) -> _Bootstrap:
    path = _cache_path()
    cached = _read_cache(path) if path is not None else None
    if cached is not None and time.time() - cached.fetched_at < CACHE_TTL_SECS:
        return cached
    try:
        fresh = await _fetch_bootstrap(http)
    except Exception:
        return _Bootstrap(bl=FALLBACK_BL, sid=FALLBACK_SID, fetched_at=time.time())
    _write_cache(path, fresh)
    return fresh


class CodeWikiClient:
    """Stateless client; the bootstrap pair is cached on disk (6h TTL)."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=30.0,
            verify=True,
            headers={"User-Agent": USER_AGENT},
            transport=self._transport,
        )

    async def read_wiki(self, repo: str) -> Wiki:
        async with self._client() as http:
            bs = await _load_bootstrap(http)
            inner = json.dumps([_github_url(repo)])
            payload = await self._call(http, bs, "VSX6ub", repo, inner)
            return parse_wiki(payload)

    async def ask(self, repo: str, question: str) -> str:
        async with self._client() as http:
            bs = await _load_bootstrap(http)
            inner = json.dumps([[[question, "user"]], [None, _github_url(repo)]])
            payload = await self._call(http, bs, "EgIxfe", repo, inner)
            if isinstance(payload, list) and payload and isinstance(payload[0], str):
                return payload[0]
            raise CodeWikiError("EgIxfe response did not contain an answer string")

    async def _call(
        self,
        http: httpx.AsyncClient,
        bs: _Bootstrap,
        rpc_id: str,
        repo: str,
        inner_json: str,
    ) -> object:
        params = {
            "rpcids": rpc_id,
            "source-path": f"/github.com/{repo}",
            "bl": bs.bl,
            "f.sid": bs.sid,
            "hl": "en-US",
            "_reqid": _pseudo_reqid(),
            "rt": "c",
        }
        headers = {
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": SITE,
            "Referer": f"{SITE}/github.com/{repo}",
            "X-Same-Domain": "1",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        }
        try:
            resp = await http.post(
                ENDPOINT,
                params=params,
                headers=headers,
                content=boq.encode_request(rpc_id, inner_json),
            )
        except httpx.TransportError as exc:
            raise CodeWikiConnectionError(f"Failed to connect to CodeWiki: {exc}") from exc
        if resp.status_code != 200:
            raise CodeWikiError(
                f"batchexecute returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            return boq.decode_response(resp.text, rpc_id)
        except ValueError as exc:
            raise CodeWikiError(str(exc)) from exc


def _github_url(repo: str) -> str:
    return f"https://github.com/{repo}"


def _pseudo_reqid() -> int:
    return 100_000 + (int(time.time()) % 900_000)

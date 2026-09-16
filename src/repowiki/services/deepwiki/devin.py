"""Reverse-engineered api.devin.ai client."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Callable
from contextlib import nullcontext
from uuid import uuid4

import httpx
import websockets
from websockets.exceptions import ConnectionClosedOK, WebSocketException

from repowiki.services.deepwiki.client import ConnectionError, ToolError
from repowiki.shared.model import Answer, Reference, SourceFile


_CITE_RE = re.compile(r"<cite\s+([^>]*?)\s*/?>")
_CITE_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def _parse_cites(body: str) -> tuple[str, list[Reference]]:
    """Replace inline ``<cite …/>`` tags with ``[i]`` markers, returning references.

    Some responses encode citations as self-closing tags carrying ``path`` and
    ``start`` (an ``X-Y`` line range) instead of separate ``reference`` events.
    """
    references: list[Reference] = []

    def _replace(match: re.Match[str]) -> str:
        attrs = dict(_CITE_ATTR_RE.findall(match.group(1)))
        path = attrs.get("path", "")
        if not path:
            return match.group(0)
        parts = attrs.get("start", "").split("-")
        try:
            range_start = int(parts[0])
            range_end = int(parts[1]) if len(parts) > 1 else range_start
        except (ValueError, IndexError):
            range_start = range_end = None
        references.append(Reference(path, range_start, range_end))
        return f"[{len(references)}]"

    return _CITE_RE.sub(_replace, body), references


def parse_response(query: dict, query_id: str | None) -> Answer:
    """Assemble an Answer from a single query block's response events."""
    body: list[str] = []
    summary: list[str] = []
    references: list[Reference] = []
    sources: list[SourceFile] = []
    seen: set[tuple[str, str]] = set()
    stats: dict[str, float] = {}

    for event in query.get("response", []):
        kind = event.get("type")
        data = event.get("data")
        if kind == "chunk":
            body.append(data)
        elif kind == "summary_chunk":
            summary.append(data)
        elif kind == "reference":
            references.append(
                Reference(
                    file_path=data["file_path"],
                    range_start=data.get("range_start"),
                    range_end=data.get("range_end"),
                )
            )
            body.append(f"[{len(references)}]")
        elif kind == "file_contents":
            repo, path, content = data
            key = (repo, path)
            if key not in seen:
                seen.add(key)
                sources.append(SourceFile(repo=repo, path=path, content=content))
        elif kind == "stats":
            stats[data["key"]] = data["value"]
        elif kind == "done":
            break

    body_text = "".join(body)
    if not references and "<cite" in body_text:
        body_text, references = _parse_cites(body_text)

    return Answer(
        body=body_text,
        summary="".join(summary) or None,
        references=references,
        sources=sources,
        stats=stats,
        query_id=query_id,
    )


DEFAULT_API_URL = "https://api.devin.ai"

ENGINE_MAP = {"fast": "multihop_faster", "deep": "agent", "codemap": "codemap"}


def _http_detail(exc: httpx.HTTPStatusError) -> str:
    """Surface FastAPI's ``{"detail": ...}`` body so the CLI can classify it."""
    try:
        detail = exc.response.json().get("detail")
    except Exception:
        return ""
    if isinstance(detail, str) and detail:
        return f": {detail}"
    return ""


class DevinClient:
    """Client for the reverse-engineered api.devin.ai Q&A endpoints."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.environ.get("DEEPWIKI_API_URL", DEFAULT_API_URL)

    async def _get_json(
        self,
        path: str,
        *,
        params: dict | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict:
        ctx = nullcontext(client) if client is not None else httpx.AsyncClient(
            base_url=self.base_url, timeout=30.0
        )
        try:
            async with ctx as c:
                resp = await c.get(path, params=params)
                resp.raise_for_status()
                return resp.json()
        except httpx.TransportError as exc:
            raise ConnectionError(f"Failed to connect to Devin server: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise ToolError(
                f"Devin API returned HTTP {exc.response.status_code}{_http_detail(exc)}"
            ) from exc

    async def _post_json(
        self,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict:
        ctx = nullcontext(client) if client is not None else httpx.AsyncClient(
            base_url=self.base_url, timeout=30.0
        )
        try:
            async with ctx as c:
                resp = await c.post(path, params=params, json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.TransportError as exc:
            raise ConnectionError(f"Failed to connect to Devin server: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise ToolError(
                f"Devin API returned HTTP {exc.response.status_code}{_http_detail(exc)}"
            ) from exc

    async def ask(
        self,
        repos: list[str],
        question: str,
        *,
        mode: str = "fast",
        query_id: str | None = None,
        timeout: float = 120.0,
        poll_interval: float = 2.0,
        context: str = "",
        generate_summary: bool = True,
        on_chunk: Callable[[str], None] | None = None,
    ) -> Answer:
        engine_id = ENGINE_MAP.get(mode)
        if engine_id is None:
            raise ToolError(f"unknown mode {mode!r}")
        qid = query_id or str(uuid4())
        payload = {
            "engine_id": engine_id,
            "user_query": question,
            "keywords": [],
            "repo_names": list(repos),
            "additional_context": context,
            "query_id": qid,
            "use_notes": False,
            "attached_context": [],
            "generate_summary": generate_summary,
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            await self._post_json("/ada/query", json=payload, client=client)
            if on_chunk is not None:
                events = await self._stream_chunks(qid, on_chunk, timeout=timeout)
                return parse_response({"response": events}, qid)
            return await self._poll_query(
                qid, client=client, poll_interval=poll_interval, timeout=timeout
            )

    async def _stream_chunks(
        self, qid: str, on_chunk: Callable[[str], None], *, timeout: float
    ) -> list[dict]:
        """Stream events over the WebSocket, emitting answer text, until 'done'.

        Chunk text and inline citation markers (``[i]`` emitted at each
        ``reference`` event) are forwarded through ``on_chunk``, so the streamed
        body shows citations inline and lines up with the final ``## Sources``.

        Returns the full event list so the caller can assemble a complete
        Answer (body, summary, references, sources) without a follow-up GET.
        """
        ws_url = f"{self.base_url.replace('http', 'ws', 1)}/ada/ws/query/{qid}"
        deadline = time.monotonic() + timeout
        events: list[dict] = []
        ref_count = 0
        try:
            async with websockets.connect(ws_url) as ws:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ToolError("timed out waiting for answer")
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    except asyncio.TimeoutError:
                        raise ToolError("timed out waiting for answer")
                    except ConnectionClosedOK:
                        break
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(msg, dict):
                        continue
                    kind = msg.get("type")
                    if kind is None:
                        continue
                    if kind == "done":
                        break
                    events.append(msg)
                    if kind == "chunk":
                        on_chunk(msg.get("data", ""))
                    elif kind == "reference":
                        ref_count += 1
                        on_chunk(f"[{ref_count}]")
        except (OSError, WebSocketException) as exc:
            raise ConnectionError(f"WebSocket connection failed: {exc}") from exc
        return events

    async def _poll_query(
        self,
        qid: str,
        *,
        client: httpx.AsyncClient,
        poll_interval: float,
        timeout: float,
    ) -> Answer:
        deadline = time.monotonic() + timeout
        while True:
            await asyncio.sleep(poll_interval)
            if time.monotonic() > deadline:
                raise ToolError("timed out waiting for answer")
            data = await self._get_json(f"/ada/query/{qid}", client=client)
            queries = data.get("queries")
            if not queries:
                raise ToolError("Devin API returned no query results")
            query = queries[-1]
            if query.get("state") in ("done", "error"):
                break
        if query.get("error"):
            raise ToolError(str(query["error"]))
        return parse_response(query, qid)

    async def list_public_indexes(self, search: str) -> dict:
        return await self._get_json("/ada/list_public_indexes", params={"search_repo": search})

    async def public_repo_indexing_status(self, repo: str) -> dict:
        return await self._get_json("/ada/public_repo_indexing_status", params={"repo_name": repo})

    async def warm_public_repo(self, repo: str) -> dict:
        return await self._post_json("/ada/warm_public_repo", params={"repo_name": repo})

    async def get_query(self, query_id: str) -> Answer:
        data = await self._get_json(f"/ada/query/{query_id}")
        queries = data.get("queries")
        if not queries:
            raise ToolError("Devin API returned no query results")
        query = queries[-1]
        if query.get("error"):
            raise ToolError(str(query["error"]))
        return parse_response(query, query_id)

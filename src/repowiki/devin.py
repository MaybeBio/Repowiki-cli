"""Reverse-engineered api.devin.ai client."""

from __future__ import annotations

import asyncio
import os
import time
from uuid import uuid4

import httpx

from repowiki.client import ConnectionError, ToolError
from repowiki.model import Answer, Reference, SourceFile


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

    return Answer(
        body="".join(body),
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

    async def ask(
        self,
        repo: str,
        question: str,
        *,
        mode: str = "fast",
        query_id: str | None = None,
        timeout: float = 120.0,
        poll_interval: float = 2.0,
    ) -> Answer:
        engine_id = ENGINE_MAP.get(mode)
        if engine_id is None:
            raise ToolError(f"unknown mode {mode!r}")
        qid = query_id or str(uuid4())
        payload = {
            "engine_id": engine_id,
            "user_query": question,
            "keywords": [],
            "repo_names": [repo],
            "additional_context": "",
            "query_id": qid,
            "use_notes": False,
            "attached_context": [],
            "generate_summary": True,
        }
        query = None
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
                resp = await client.post("/ada/query", json=payload)
                resp.raise_for_status()
                deadline = time.monotonic() + timeout
                while True:
                    await asyncio.sleep(poll_interval)
                    resp = await client.get(f"/ada/query/{qid}")
                    resp.raise_for_status()
                    queries = resp.json().get("queries")
                    if not queries:
                        raise ToolError("Devin API returned no query results")
                    query = queries[-1]
                    if query.get("state") in ("done", "error"):
                        break
                    if time.monotonic() > deadline:
                        raise ToolError("timed out waiting for answer")
        except httpx.TransportError as exc:
            raise ConnectionError(f"Failed to connect to Devin server: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise ToolError(
                f"Devin API returned HTTP {exc.response.status_code}{_http_detail(exc)}"
            ) from exc
        assert query is not None
        if query.get("error"):
            raise ToolError(str(query["error"]))
        return parse_response(query, qid)

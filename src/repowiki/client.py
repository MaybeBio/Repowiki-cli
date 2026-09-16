"""MCP client wrapper for the DeepWiki API."""

from __future__ import annotations

import logging
import os
from contextlib import AsyncExitStack
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from repowiki.shared.model import Answer

logging.getLogger("httpx_sse").setLevel(logging.ERROR)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.ERROR)

DEFAULT_MCP_URL = "https://mcp.deepwiki.com/mcp"


class DeepWikiError(Exception):
    """Base exception for DeepWiki errors."""


class ConnectionError(DeepWikiError):
    """Failed to connect to the DeepWiki server."""


class ToolError(DeepWikiError):
    """Error returned from an MCP tool execution."""


def _root_cause(exc: BaseException) -> BaseException:
    """Unwrap an exception group (Python 3.11+) to its first leaf cause."""
    while (sub := getattr(exc, "exceptions", None)):
        exc = sub[0]
    return exc


def _is_connection_failure(exc: BaseException) -> bool:
    if isinstance(exc, (OSError, httpx.TransportError)):
        return True
    message = str(exc).lower()
    return "connection" in message or "timeout" in message


class DeepWikiClient:
    """Client for interacting with DeepWiki via MCP.

    Can be used one-shot (each call opens and closes its own connection) or as
    a persistent session via the async context manager, which reuses a single
    connection across calls — the REPL uses this to avoid re-handshaking per
    question.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.environ.get("DEEPWIKI_MCP_URL", DEFAULT_MCP_URL)
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    # -- persistent session management -------------------------------------

    async def __aenter__(self) -> "DeepWikiClient":
        await self.open()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def open(self) -> None:
        """Open and initialize a session, retrying once on connection failure."""
        last: ConnectionError | None = None
        for _ in range(2):
            try:
                await self._open_once()
                return
            except ConnectionError as exc:
                last = exc
        assert last is not None
        raise last

    async def close(self) -> None:
        """Close the open session, if any."""
        stack, self._stack = self._stack, None
        self._session = None
        if stack is not None:
            await stack.aclose()

    async def _open_once(self) -> None:
        stack = AsyncExitStack()
        try:
            read, write, _ = await stack.enter_async_context(
                streamablehttp_client(self.base_url)
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except Exception as exc:
            await stack.aclose()
            root = _root_cause(exc)
            if _is_connection_failure(root):
                raise ConnectionError(
                    f"Failed to connect to DeepWiki server: {root}"
                ) from exc
            raise ToolError(f"Failed to initialize MCP session: {root}") from exc
        self._stack = stack
        self._session = session

    # -- tool calls ---------------------------------------------------------

    async def _invoke(self, tool_name: str, arguments: dict[str, Any]) -> str:
        assert self._session is not None
        try:
            result = await self._session.call_tool(tool_name, arguments)
        except Exception as exc:
            root = _root_cause(exc)
            if _is_connection_failure(root):
                raise ConnectionError(
                    f"Failed to connect to DeepWiki server: {root}"
                ) from exc
            raise ToolError(f"Tool '{tool_name}' failed: {root}") from exc
        return self._extract_text_content(result)

    async def _call_oneshot(self, tool_name: str, arguments: dict[str, Any]) -> str:
        try:
            await self.open()
            return await self._invoke(tool_name, arguments)
        finally:
            await self.close()

    async def _call_persistent(self, tool_name: str, arguments: dict[str, Any]) -> str:
        for attempt in range(2):
            try:
                return await self._invoke(tool_name, arguments)
            except ConnectionError as exc:
                if attempt == 0:
                    await self.close()
                    await self.open()
                    continue
                raise

    def _extract_text_content(self, result: Any) -> str:
        parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
        text = "\n".join(parts)
        if result.isError:
            raise ToolError(text or "Unknown tool error")
        return text

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if self._session is None:
            return await self._call_oneshot(tool_name, arguments)
        return await self._call_persistent(tool_name, arguments)

    async def read_wiki_structure(self, repo_name: str) -> str:
        return await self._call_tool("read_wiki_structure", {"repoName": repo_name})

    async def read_wiki_contents(self, repo_name: str) -> str:
        return await self._call_tool("read_wiki_contents", {"repoName": repo_name})

    async def ask_question(self, repo_name: str, question: str) -> Answer:
        text = await self._call_tool(
            "ask_question", {"repoName": repo_name, "question": question}
        )
        return Answer(body=text)

"""MCP client wrapper for the DeepWiki API."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logging.getLogger("httpx_sse").setLevel(logging.ERROR)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.ERROR)

DEFAULT_MCP_URL = "https://mcp.deepwiki.com/mcp"


class DeepWikiError(Exception):
    """Base exception for DeepWiki errors."""


class ConnectionError(DeepWikiError):
    """Failed to connect to the DeepWiki server."""


class ToolError(DeepWikiError):
    """Error returned from an MCP tool execution."""


class DeepWikiClient:
    """Client for interacting with DeepWiki via MCP."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.environ.get("DEEPWIKI_MCP_URL", DEFAULT_MCP_URL)

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        try:
            async with streamablehttp_client(self.base_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    return self._extract_text_content(result)
        except DeepWikiError:
            raise
        except Exception as exc:
            message = str(exc).lower()
            if "connection" in message or "timeout" in message:
                raise ConnectionError(f"Failed to connect to DeepWiki server: {exc}") from exc
            raise ToolError(f"Tool '{tool_name}' failed: {exc}") from exc

    def _extract_text_content(self, result: Any) -> str:
        parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
        text = "\n".join(parts)
        if result.isError:
            raise ToolError(text or "Unknown tool error")
        return text

    async def read_wiki_structure(self, repo_name: str) -> str:
        return await self._call_tool("read_wiki_structure", {"repoName": repo_name})

    async def read_wiki_contents(self, repo_name: str) -> str:
        return await self._call_tool("read_wiki_contents", {"repoName": repo_name})

    async def ask_question(self, repo_name: str, question: str) -> str:
        return await self._call_tool(
            "ask_question", {"repoName": repo_name, "question": question}
        )


def run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)

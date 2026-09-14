"""Output formatting for CLI results."""

from __future__ import annotations


def format_header(repo: str, command: str) -> str:
    """Return the Markdown header line identifying a result."""
    return f"## DeepWiki: {repo} ({command})"


def format_result(repo: str, command: str, text: str) -> str:
    """Wrap result text in a Markdown header, trimming surrounding whitespace."""
    return f"{format_header(repo, command)}\n\n{text.strip()}"

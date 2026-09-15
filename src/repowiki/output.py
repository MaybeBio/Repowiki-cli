"""Output formatting for CLI results."""

from __future__ import annotations

import json
import re
import sys
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.markdown import Markdown

_PAGE_DELIMITER = re.compile(r"^# Page: (.*)$", re.MULTILINE)
_DETAILS_TAG = re.compile(r"</?details[^>]*>", re.IGNORECASE)
_SUMMARY_TAG = re.compile(r"<summary[^>]*>(.*?)</summary>", re.IGNORECASE | re.DOTALL)


def format_header(repo: str, command: str) -> str:
    """Return the Markdown header line identifying a result."""
    return f"## DeepWiki: {repo} ({command})"


def format_result(repo: str, command: str, text: str) -> str:
    """Wrap result text in a Markdown header, trimming surrounding whitespace."""
    return f"{format_header(repo, command)}\n\n{text.strip()}"


def format_json(repo: str, command: str, **fields: object) -> str:
    """Return a machine-readable JSON envelope for a result."""
    return json.dumps(
        {"repo": repo, "command": command, **fields},
        indent=2,
        ensure_ascii=False,
    )


def format_error_json(kind: str, message: str) -> str:
    """Return a single-line JSON error object."""
    return json.dumps({"error": message, "kind": kind}, ensure_ascii=False)


def list_page_titles(text: str) -> list[str]:
    """Return page titles found after each '# Page:' delimiter."""
    return [m.group(1).strip() for m in _PAGE_DELIMITER.finditer(text)]


def filter_page(text: str, title: str) -> str:
    """Return the content of the page whose title matches (case-insensitive exact).

    Raises ValueError if no page matches.
    """
    matches = list(_PAGE_DELIMITER.finditer(text))
    target = title.strip().lower()
    available = []
    for i, m in enumerate(matches):
        page_title = m.group(1).strip()
        available.append(page_title)
        if page_title.lower() == target:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[m.end() : end].strip()
    listing = "\n".join(f"  - {t}" for t in available) or "  - (none)"
    raise ValueError(f"Page '{title}' not found. Available pages:\n{listing}")


def _prepare_markdown(text: str) -> str:
    """Convert HTML that rich's Markdown renderer would silently drop."""
    text = _DETAILS_TAG.sub("", text)
    text = _SUMMARY_TAG.sub(lambda m: f"**{m.group(1).strip()}**", text)
    return text


def render_markdown(text: str) -> None:
    """Render Markdown text to the terminal via rich."""
    Console().print(Markdown(_prepare_markdown(text)))


@contextmanager
def status(message: str) -> Iterator[None]:
    """Show a spinner on stderr while a slow call runs.

    No-op when stderr is not a terminal, so piped output and tests stay clean.
    """
    if not sys.stderr.isatty():
        yield
        return
    with Console(stderr=True).status(message):
        yield

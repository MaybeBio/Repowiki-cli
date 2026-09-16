"""Output formatting for CLI results."""

from __future__ import annotations

import json
import re
import sys
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.markdown import Markdown

from repowiki.model import Answer, Reference, SourceFile

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


def format_command_json(command: str, **fields: object) -> str:
    """Return a JSON envelope without a repo field (for management commands)."""
    return json.dumps({"command": command, **fields}, indent=2, ensure_ascii=False)


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


def _clean_path(file_path: str) -> str:
    """Strip a leading 'Repo owner/repo: ' prefix from a reference path."""
    if ": " in file_path:
        return file_path.split(": ", 1)[1]
    return file_path


def _range_label(path: str, start: int | None, end: int | None) -> str:
    """Format a path with its line range, omitting the range when absent.

    The reverse API uses ``None`` or ``0`` to mean "no specific lines", so
    either renders as just the path.
    """
    if not start and not end:
        return path
    return f"{path}:{start}-{end}"


def _render_slice(ref: Reference, sources: list[SourceFile]) -> str | None:
    path = _clean_path(ref.file_path)
    src = next((s for s in sources if s.path == path), None)
    if src is None:
        return None
    lines = src.content.split("\n")
    start = ref.range_start if ref.range_start else 1
    end = ref.range_end if ref.range_end else len(lines)
    lo = max(0, start - 1)
    hi = min(len(lines), end)
    numbered = "\n".join(f"{n:4d} {lines[n - 1]}" for n in range(lo + 1, hi + 1))
    return f"```\n{_range_label(path, ref.range_start, ref.range_end)}\n{numbered}\n```"


def _format_sources(references: list[Reference], sources: list[SourceFile], show_sources: bool) -> str:
    lines = ["## Sources", ""]
    for i, ref in enumerate(references, 1):
        path = _clean_path(ref.file_path)
        lines.append(f"{i}. {_range_label(path, ref.range_start, ref.range_end)}")
        if show_sources:
            slice_text = _render_slice(ref, sources)
            if slice_text:
                lines.extend(["", slice_text])
    return "\n".join(lines)


def format_answer(answer: Answer, *, show_sources: bool = False) -> str:
    """Render an Answer as Markdown (no outer header)."""
    body = answer.body
    parts = [body.strip()]
    if answer.summary:
        parts.append(f"## Summary\n\n{answer.summary.strip()}")
    if answer.references:
        parts.append(_format_sources(answer.references, answer.sources, show_sources))
    return "\n\n".join(parts)


def format_answer_tail(answer: Answer, *, show_sources: bool = False) -> str:
    """Render an Answer's summary and sources (no body) for streamed output."""
    parts = []
    if answer.summary:
        parts.append(f"## Summary\n\n{answer.summary.strip()}")
    if answer.references:
        parts.append(_format_sources(answer.references, answer.sources, show_sources))
    return "\n\n".join(parts)


def format_list(result: dict) -> str:
    """Render a list_public_indexes result as one line per indexed repo."""
    indices = result.get("indices") or []
    if not indices:
        return "No matching indexed repos."
    lines = []
    for entry in indices:
        repo = entry.get("repo_name", "")
        bits = []
        if entry.get("last_modified"):
            bits.append(entry["last_modified"])
        if entry.get("language"):
            bits.append(entry["language"])
        if entry.get("stargazers_count") is not None:
            bits.append(f"{entry['stargazers_count']} stars")
        suffix = f" ({', '.join(bits)})" if bits else ""
        lines.append(f"- {repo}{suffix}")
    return "\n".join(lines)


def format_status(repo: str, result: dict) -> str:
    return f"{repo}: {result.get('status', 'unknown')}"


def format_warm(repo: str, result: dict) -> str:
    return f"warmed {repo} ({result.get('status', 'OK')})"

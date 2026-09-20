"""Models and pure-function transforms for zread.ai wiki data."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Page:
    page_id: str
    slug: str
    topic: str
    section: str = ""
    group: str = ""
    order: int = 0


@dataclass
class WikiInfo:
    wiki_id: str = ""
    repo_id: str = ""


_CALLOUT_RE = re.compile(r"<Cgx(?P<kind>[A-Za-z]+)>(?P<body>.*?)</Cgx(?P=kind)>", re.S)
_FENCE_OPEN_RE = re.compile(r"^\s{0,3}(```+|~~~+)")

_CALLOUT_KIND = {
    "tip": "TIP",
    "note": "NOTE",
    "info": "NOTE",
    "warn": "WARNING",
    "warning": "WARNING",
    "caution": "CAUTION",
    "important": "CAUTION",
    "danger": "CAUTION",
}


def parse_wiki_data(data: dict) -> tuple[WikiInfo, list[Page]]:
    """Build ``(WikiInfo, pages)`` from the ``GET /api/v1/wiki/{wiki_id}`` body."""
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    wiki_info = WikiInfo(
        wiki_id=str(info.get("wiki_id") or ""),
        repo_id=str(info.get("repo_id") or ""),
    )
    pages = []
    raw_pages = data.get("pages") if isinstance(data.get("pages"), list) else []
    for i, p in enumerate(raw_pages):
        if not isinstance(p, dict):
            continue
        slug = (p.get("slug") or "").strip()
        if not slug:
            continue
        pages.append(
            Page(
                page_id=str(p.get("page_id") or ""),
                slug=slug,
                topic=(p.get("topic") or slug).strip(),
                section=(p.get("section") or "").strip(),
                group=(p.get("group") or "").strip(),
                order=int(p.get("order", i) or 0),
            )
        )
    pages.sort(key=lambda p: p.order)
    for i, p in enumerate(pages):
        p.order = i
    return wiki_info, pages


def _code_spans(md: str) -> list[tuple[int, int]]:
    spans = []
    pos = 0
    fence = None
    start = 0
    for line in md.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        if fence is None:
            m = _FENCE_OPEN_RE.match(stripped)
            if m:
                fence = m.group(1)[0] * 3
                start = pos
        elif stripped.strip().startswith(fence):
            spans.append((start, pos + len(line)))
            fence = None
        pos += len(line)
    if fence is not None:
        spans.append((start, len(md)))
    return spans


def _in_spans(idx: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= idx < b for a, b in spans)


def rewrite_callouts(md: str) -> str:
    """Convert ``<CgxTip>…</CgxTip>`` shells to GitHub ``> [!TIP]`` blocks."""
    spans = _code_spans(md)

    def sub(m: re.Match) -> str:
        if _in_spans(m.start(), spans):
            return m.group(0)
        kind = _CALLOUT_KIND.get(m.group("kind").lower(), "NOTE")
        body = m.group("body").strip()
        if not body:
            return ""
        lines = "\n".join(f"> {ln}".rstrip() for ln in body.split("\n"))
        return f"> [!{kind}]\n{lines}"

    return _CALLOUT_RE.sub(sub, md)


def strip_frontmatter(md: str) -> str:
    """Remove a leading ``---\n…\n---`` YAML frontmatter block."""
    m = re.match(r"^---\n.*?\n---\n\n?", md, re.S)
    return md[m.end():] if m else md

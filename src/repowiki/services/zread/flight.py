"""Pure-function parsing of zread.ai Next.js RSC flight payloads.

The site embeds its data in ``self.__next_f.push([1,"..."])`` script tags.  Long
text blobs inside the flight payload use the ``NN:T<hexlen>,`` prefix, where
``hexlen`` is a **UTF-8 byte** count (not a character count).
"""

from __future__ import annotations

import json
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


_FLIGHT_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_TBLOB_RE = re.compile(rb"([0-9a-f]+):T([0-9a-f]+),")
_WIKI_VALUE_RE = re.compile(r'"wiki":\s*(?=\{)')
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


def extract_flight(html: str) -> str:
    """Concatenate and unescape every ``self.__next_f.push([1,"..."])`` chunk."""
    chunks = []
    for raw in _FLIGHT_RE.findall(html):
        try:
            chunks.append(json.loads('"' + raw + '"'))
        except json.JSONDecodeError:
            continue
    return "".join(chunks)


def _text_blobs(payload: str) -> list[str]:
    """Decode long-text ``NN:T<hexlen>,`` lines, slicing on UTF-8 bytes."""
    raw = payload.encode("utf-8")
    out = []
    for m in _TBLOB_RE.finditer(raw):
        length = int(m.group(2), 16)
        out.append(raw[m.end():m.end() + length].decode("utf-8", "replace"))
    return out


def extract_markdown(payload: str, slug: str | None = None) -> str | None:
    """Return the page markdown blob (the one whose frontmatter matches *slug*)."""
    cands = [b for b in _text_blobs(payload) if b.lstrip().startswith("---\nslug:")]
    if not cands:
        return None
    if slug:
        exact = [b for b in cands if re.search(rf"(?m)^slug:\s*{re.escape(slug)}\s*$", b)]
        if exact:
            return max(exact, key=len)
    return max(cands, key=len)


def parse_wiki(payload: str) -> tuple[WikiInfo, list[Page]] | None:
    """Find the ``{"wiki": {"info": ..., "pages": [...]}}`` node and flatten it."""
    dec = json.JSONDecoder()
    for m in _WIKI_VALUE_RE.finditer(payload):
        try:
            wiki, _ = dec.raw_decode(payload, m.end())
        except json.JSONDecodeError:
            continue
        if not (
            isinstance(wiki, dict)
            and isinstance(wiki.get("info"), dict)
            and isinstance(wiki.get("pages"), list)
            and wiki["pages"]
        ):
            continue
        info = wiki["info"]
        wiki_info = WikiInfo(
            wiki_id=str(info.get("wiki_id") or ""),
            repo_id=str(info.get("repo_id") or ""),
        )
        pages = []
        for i, p in enumerate(wiki["pages"]):
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
    return None


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

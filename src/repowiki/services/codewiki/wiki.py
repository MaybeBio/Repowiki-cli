"""Parse and render CodeWiki VSX6ub wiki payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import unquote

_GITHUB_PREFIX = "https://github.com"


@dataclass
class Section:
    title: str
    level: int
    markdown: str
    diagrams: list[str] = field(default_factory=list)


@dataclass
class Wiki:
    repo_slug: str
    commit_sha: str
    sections: list[Section]


def parse(payload: object) -> Wiki:
    """Parse a VSX6ub payload: ``[wiki, [null, url], true, n]``."""
    if not isinstance(payload, list) or not payload:
        raise ValueError("missing wiki container")
    container = payload[0]
    if not isinstance(container, list) or not container:
        raise ValueError("missing wiki container")
    header = container[0]
    if not isinstance(header, list) or not header:
        raise ValueError("missing wiki header array")
    repo_slug = header[0] if header and isinstance(header[0], str) else ""
    if not repo_slug:
        raise ValueError("missing repo slug")
    commit_sha = header[1] if len(header) > 1 and isinstance(header[1], str) else ""
    raw_sections = container[1] if len(container) > 1 else None
    if not isinstance(raw_sections, list):
        raise ValueError("missing sections array")
    sections = [parse_section(s, i) for i, s in enumerate(raw_sections)]
    return Wiki(repo_slug=repo_slug, commit_sha=commit_sha, sections=sections)


def parse_section(value: object, index: int) -> Section:
    if not isinstance(value, list):
        raise ValueError(f"section #{index} is not an array")
    title = value[0] if value and isinstance(value[0], str) else ""
    if not title:
        raise ValueError(f"missing title in section #{index}")
    level = value[1] if len(value) > 1 and isinstance(value[1], int) else 1
    markdown = ""
    if len(value) > 5 and isinstance(value[5], str):
        markdown = value[5]
    elif len(value) > 4 and isinstance(value[4], str):
        markdown = value[4]
    diagrams = extract_diagrams(value[7] if len(value) > 7 else None)
    return Section(title=title, level=level, markdown=markdown, diagrams=diagrams)


def extract_diagrams(outer: object) -> list[str]:
    out: list[str] = []
    if not isinstance(outer, list):
        return out
    for group in outer:
        if not isinstance(group, list):
            continue
        for diagram in group:
            if not isinstance(diagram, list):
                continue
            if len(diagram) > 4 and isinstance(diagram[4], str) and diagram[4]:
                out.append(diagram[4])
    return out


def render_structure(wiki: Wiki) -> str:
    lines = []
    for s in wiki.sections:
        indent = "  " * max(0, s.level - 1)
        lines.append(f"{indent}- {s.title}")
    return "\n".join(lines) + ("\n" if lines else "")


def render_markdown(wiki: Wiki) -> str:
    parts = [f"# {wiki.repo_slug} (commit {wiki.commit_sha})\n"]
    for s in wiki.sections:
        hashes = "#" * min(max(s.level, 1), 6)
        parts.append(f"{hashes} {s.title}\n")
        body = resolve_links(s.markdown)
        parts.append(body)
        if body and not body.endswith("\n"):
            parts.append("\n")
        for dot in s.diagrams:
            parts.append(f"\n```dot\n{dot.strip()}\n```\n")
        parts.append("\n")
    return "".join(parts)


def resolve_links(markdown: str) -> str:
    """Rewrite ``](%2F...)`` / ``](/...)`` targets to ``](https://github.com/...)``."""
    out: list[str] = []
    rest = markdown
    while True:
        open_idx = rest.find("](")
        if open_idx == -1:
            out.append(rest)
            break
        out.append(rest[:open_idx])
        after = rest[open_idx + 2:]
        end = _find_link_end(after)
        if end is None:
            out.append("](")
            rest = after
            continue
        out.append("](")
        out.append(_rewrite_target(after[:end]))
        out.append(")")
        rest = after[end + 1:]
    return "".join(out)


def _find_link_end(s: str) -> int | None:
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                return i
            depth -= 1
    return None


def _rewrite_target(target: str) -> str:
    needs_rewrite = target.startswith(("%2F", "%2f", "/"))
    if not needs_rewrite:
        return target
    decoded = unquote(target)
    if decoded.startswith("/"):
        return f"{_GITHUB_PREFIX}{decoded}"
    return decoded

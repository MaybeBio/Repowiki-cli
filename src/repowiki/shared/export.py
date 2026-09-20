"""Export wiki pages as Markdown files plus llms.txt / README.md indexes."""

from __future__ import annotations

import re
from pathlib import Path


def _safe_name(title: str, index: int) -> str:
    """Turn a page title into a filesystem-safe ``NN-name.md`` filename."""
    slug = re.sub(r"[^\w\-]+", "-", title.strip()).strip("-").lower() or "page"
    return f"{index:02d}-{slug}.md"


def export_pages(out_dir: str, repo: str, pages: list[tuple[str, str]], full: str) -> int:
    """Write one file per page plus ``llms.txt`` / ``README.md`` / ``llms-full.txt``.

    ``pages`` is a list of ``(title, markdown)``; ``full`` is the complete
    concatenated markdown. ``llms.txt`` and ``README.md`` carry the same page
    index (``README.md`` for GitHub auto-rendering). Returns the page count.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[str, str]] = []
    for i, (title, markdown) in enumerate(pages):
        fname = _safe_name(title, i)
        (out / fname).write_text(markdown, encoding="utf-8")
        entries.append((title, fname))
    index = ["# " + repo, ""]
    for title, fname in entries:
        index.append(f"- [{title}]({fname})")
    index_text = "\n".join(index) + "\n"
    (out / "llms.txt").write_text(index_text, encoding="utf-8")
    (out / "README.md").write_text(index_text, encoding="utf-8")
    (out / "llms-full.txt").write_text(full + "\n", encoding="utf-8")
    return len(entries)

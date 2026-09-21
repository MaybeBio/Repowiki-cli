"""Export wiki pages as Markdown files plus llms.txt / README.md indexes."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path


def _safe_name(title: str, index: int) -> str:
    """Turn a page title into a filesystem-safe ``NN-name.md`` filename."""
    slug = re.sub(r"[^\w\-]+", "-", title.strip()).strip("-").lower() or "page"
    return f"{index:02d}-{slug}.md"


async def fetch_pages(items, fetch, concurrency: int = 5) -> list:
    """Concurrently call ``fetch(item)`` for each item, preserving order.

    ``fetch`` is an async function returning one result per item; used by
    services whose pages must be downloaded individually (e.g. Zread).
    """
    sem = asyncio.Semaphore(concurrency)

    async def one(item):
        async with sem:
            return await fetch(item)

    return await asyncio.gather(*(one(item) for item in items))


def _write(out_dir: str, repo: str, entries: list[tuple[str, str, str]], full: str) -> int:
    """Write one ``(filename, title, markdown)`` per page plus the indexes."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = ["# " + repo, ""]
    for filename, title, markdown in entries:
        (out / filename).write_text(markdown, encoding="utf-8")
        index.append(f"- [{title}]({filename})")
    index_text = "\n".join(index) + "\n"
    (out / "llms.txt").write_text(index_text, encoding="utf-8")
    (out / "README.md").write_text(index_text, encoding="utf-8")
    (out / "llms-full.txt").write_text(full + "\n", encoding="utf-8")
    return len(entries)


def export_pages(out_dir: str, repo: str, pages: list[tuple[str, str]], full: str) -> int:
    """Write one file per page plus ``llms.txt`` / ``README.md`` / ``llms-full.txt``.

    ``pages`` is a list of ``(title, markdown)``; each page is named
    ``NN-slug.md`` from its title. ``full`` is the complete concatenated
    markdown. Returns the page count.
    """
    entries = [(_safe_name(title, i), title, markdown) for i, (title, markdown) in enumerate(pages)]
    return _write(out_dir, repo, entries, full)


def export_pages_named(out_dir: str, repo: str, entries: list[tuple[str, str, str]], full: str) -> int:
    """Like :func:`export_pages`, but each entry already carries its filename.

    ``entries`` is a list of ``(filename, title, markdown)`` — used by services
    (e.g. Zread) that keep the upstream native slug as the filename.
    """
    return _write(out_dir, repo, entries, full)

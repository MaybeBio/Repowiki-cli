"""Persist ask Q&A records to Markdown files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def default_save_path(repo: str) -> str:
    """Return an auto-generated Markdown filename for a repo's Q&A session."""
    slug = repo.replace("/", "-")
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"repowiki-{slug}_{stamp}.md"


def append_entry(path: str, repo: str, question: str, answer: str) -> None:
    """Append a single Q&A record to *path*, creating parent directories."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"## {repo} · {timestamp}\n\n"
        f"**Q:** {question}\n\n"
        f"{answer.strip()}\n\n"
        f"---\n\n"
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(entry)

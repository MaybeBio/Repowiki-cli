"""Persist ask Q&A records to Markdown files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from typer.core import TyperCommand

# Sentinel injected into argv for a bare ``--save`` (no value). ``save`` then
# resolves to an auto-generated filename instead of an explicit path.
SAVE_AUTO = "\x00auto\x00"


def normalize_save(args: list[str]) -> list[str]:
    """Turn a bare ``--save`` into ``--save <sentinel>`` so typer accepts it.

    Typer has no support for Click's optional-value flags (``flag_value``), so a
    value-taking ``--save`` normally rejects a bare ``--save``. Rewriting the
    bare form here lets a single option cover both ``--save`` and
    ``--save PATH``.
    """
    out: list[str] = []
    i = 0
    while i < len(args):
        tok = args[i]
        out.append(tok)
        if tok == "--save":
            if i + 1 >= len(args) or args[i + 1].startswith("-"):
                out.append(SAVE_AUTO)
            else:
                out.append(args[i + 1])
                i += 1
        i += 1
    return out


class AutoSaveCommand(TyperCommand):
    """A ``TyperCommand`` that rewrites bare ``--save`` before parsing."""

    def parse_args(self, ctx, args):
        return super().parse_args(ctx, normalize_save(args))


def default_save_path(repo: str) -> str:
    """Return an auto-generated Markdown filename for a repo's Q&A session."""
    slug = repo.replace("/", "-")
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"repowiki-{slug}_{stamp}.md"


def append_entry(path: str, repo: str, question: str, answer: str) -> None:
    """Append a single Q&A record to *path*, creating parent directories."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"# {repo} · {timestamp}\n\n"
        f"> **Q:** {question}\n\n"
        f"{answer.strip()}\n\n"
        f"---\n\n"
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(entry)

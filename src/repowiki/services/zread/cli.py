"""CLI commands for the Zread service."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import NoReturn, Optional

import typer

from repowiki.services.zread.client import (
    ZreadChallengeError,
    ZreadClient,
    ZreadConnectionError,
    ZreadError,
    ZreadNotFoundError,
)
from repowiki.services.zread.flight import Page
from repowiki.shared.async_ import run_async
from repowiki.shared.model import Answer
from repowiki.shared.output import (
    format_answer,
    format_error_json,
    format_header,
    format_json,
    format_result,
    render_markdown as render_rich,
    status,
)
from repowiki.shared.repo import normalize_repo
from repowiki.shared.save import append_entry

zread_app = typer.Typer(add_completion=False, help="Query zread.ai documentation.")


def register(app: typer.Typer) -> None:
    """Mount the Zread service commands on the root app."""
    app.add_typer(zread_app, name="zread")


def _mock_text() -> Optional[str]:
    return os.environ.get("REPOWIKI_ZREAD_MOCK") or None


def _resolve_repo(raw: str, json_mode: bool) -> str:
    try:
        return normalize_repo(raw)
    except ValueError as exc:
        _fail(str(exc), "invalid_repo", json_mode)


_BLOB_RE = re.compile(r"/blob/[^/]+/(.+)$")
_LINE_FRAG_RE = re.compile(r"#L(\d+)(?:-L(\d+))?$")


def _parse_repo_arg(raw: str) -> tuple[str, str | None, int | None, int | None]:
    """Split a repo arg into ``(repo_ref, file_path, start, end)``.

    Accepts GitHub blob URLs with an optional ``#L10`` / ``#L10-L20`` line
    fragment, e.g. ``github.com/o/r/blob/main/src/a.py#L10-L20``.
    """
    value = raw.strip()
    start: int | None = None
    end: int | None = None
    m = _LINE_FRAG_RE.search(value)
    if m:
        start = int(m.group(1))
        if m.group(2):
            end = int(m.group(2))
        value = value[:m.start()].rstrip("/")
    file_path: str | None = None
    bm = _BLOB_RE.search(value)
    if bm:
        file_path = bm.group(1)
        value = value[:bm.start()]
    return value, file_path, start, end


def _fail(message: str, kind: str, json_mode: bool) -> NoReturn:
    if json_mode:
        typer.echo(format_error_json(kind, message), err=True)
    else:
        typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code={"connection": 3}.get(kind, 1))


def _handle_exception(exc: Exception, json_mode: bool) -> NoReturn:
    if isinstance(exc, ZreadConnectionError):
        _fail(str(exc), "connection", json_mode)
    elif isinstance(exc, ZreadNotFoundError):
        _fail(str(exc), "not_found", json_mode)
    elif isinstance(exc, ZreadChallengeError):
        _fail(str(exc), "challenge", json_mode)
    elif isinstance(exc, ZreadError):
        _fail(str(exc), "error", json_mode)
    _fail(f"Unexpected error: {exc}", "unexpected", json_mode)


def _emit(
    repo: str, command: str, text: str, rich: bool, json_mode: bool, **json_fields: object
) -> None:
    if json_mode:
        typer.echo(format_json(repo, command, **json_fields))
        return
    rendered = format_result("Zread", repo, command, text)
    if rich:
        render_rich(rendered)
    else:
        typer.echo(rendered)


def _resolve_lang(lang: Optional[str]) -> str:
    return lang or os.environ.get("ZREAD_LANG") or "en"


def _resolve_model(model: Optional[str]) -> str:
    return model or os.environ.get("ZREAD_MODEL") or "glm-5.1"


def _make_client(
    lang: Optional[str], model: Optional[str] = None, token: Optional[str] = None
) -> ZreadClient:
    return ZreadClient(
        lang=_resolve_lang(lang),
        model=_resolve_model(model),
        token=token or os.environ.get("ZREAD_TOKEN") or None,
    )


def _repl_prompt() -> str:
    if not sys.stdout.isatty():
        return ">> "
    return typer.style(">> ", fg=typer.colors.CYAN, bold=True)


def _print_error(exc: Exception) -> None:
    if isinstance(exc, ZreadError):
        message = str(exc)
    else:
        message = f"Unexpected error: {exc}"
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)


def _append_save(path: Optional[str], repo: str, question: str, answer: str) -> None:
    if path is None:
        return
    try:
        append_entry(path, repo, question, answer)
    except OSError as exc:
        typer.secho(f"Warning: could not save to {path}: {exc}", fg=typer.colors.YELLOW, err=True)


async def _repl(
    resolved: str, rich: bool, save_path: Optional[str], model: Optional[str], lang: Optional[str]
) -> None:
    prompt = _repl_prompt()
    client = _make_client(lang, model)
    while True:
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            typer.echo()
            break
        q = line.strip()
        if not q:
            continue
        if q in ("/exit", "/quit", "/q"):
            break
        try:
            with status("Thinking..."):
                answer = await client.ask(resolved, q)
        except Exception as exc:
            _print_error(exc)
            continue
        _append_save(save_path, resolved, q, answer)
        typer.echo()
        if rich:
            render_rich(answer.strip())
        else:
            typer.echo(answer.strip())
        typer.echo()


def _render_structure(pages: list[Page]) -> str:
    lines = []
    for p in pages:
        parts = [x for x in (p.section, p.group, p.topic) if x]
        title = "/".join(parts) if parts else p.slug
        lines.append(f"{p.order:02d}  {title}  ({p.slug})")
    return "\n".join(lines)


def _repo_name(item: dict) -> str:
    for key in ("name", "repo", "repo_name", "full_name", "slug"):
        if item.get(key):
            return str(item[key])
    owner = item.get("owner")
    if owner:
        name = item.get("name")
        return f"{owner}/{name}" if name else str(owner)
    return str(item.get("id", "?"))


def _format_repos(items: list) -> str:
    if not items:
        return "No results."
    lines = []
    for it in items:
        name = _repo_name(it)
        bits = []
        for key in ("language", "lang"):
            if it.get(key):
                bits.append(str(it[key]))
        stars = it.get("stars", it.get("stargazers_count"))
        if stars is not None:
            bits.append(f"{stars} stars")
        suffix = f" ({', '.join(bits)})" if bits else ""
        lines.append(f"- {name}{suffix}")
    return "\n".join(lines)


def _format_trending(groups: list) -> str:
    if not groups:
        return "No results."
    lines = []
    for g in groups:
        lines.append(f"## {g.get('title') or g.get('time_span') or ''}")
        for r in g.get("repos", []):
            lines.append(f"- {_repo_name(r)}")
        lines.append("")
    return "\n".join(lines).strip()


def _human_time(ts: object) -> str:
    try:
        return datetime.fromtimestamp(int(ts)).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except (TypeError, ValueError, OSError):
        return str(ts)


def _format_last_commit(value: object, human: bool) -> str:
    if not isinstance(value, dict):
        return str(value)
    parts = []
    for k, v in value.items():
        if human and k == "when":
            parts.append(f"'when': {v} ({_human_time(v)})")
        else:
            parts.append(f"{k!r}: {v!r}")
    return "{" + ", ".join(parts) + "}"


def _format_stat(data: dict, human: bool = False) -> str:
    if not data:
        return "No data."
    lines = []
    for k, v in data.items():
        if human and k in ("created_at", "updated_at"):
            lines.append(f"- {k}: {v} ({_human_time(v)})")
        elif k == "last_commit":
            lines.append(f"- {k}: {_format_last_commit(v, human)}")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def _format_stale(info: dict) -> str:
    zread_sha = info.get("zread_sha") or ""
    github_sha = info.get("github_sha") or ""
    when = info.get("github_when") or ""
    if not github_sha:
        return "Could not fetch GitHub HEAD."
    if not zread_sha:
        return "No last_commit.hash in zread data."
    if zread_sha == github_sha:
        return f"最新 (up-to-date): {github_sha}"
    suffix = f" ({when})" if when else ""
    return f"过期 (stale): zread {zread_sha[:7]} != github {github_sha[:7]}{suffix}"


def _format_search(results: list) -> str:
    if not results:
        return "No results."
    lines = []
    for r in results:
        title = str(r.get("title") or "").strip()
        slug = str(r.get("slug") or "").strip()
        heading = title or slug
        if title and slug and slug != title:
            heading = f"{title}  ({slug})"
        lines.append(f"## {heading}")
        for m in r.get("matches", []):
            if isinstance(m, dict):
                text = m.get("highlight") or m.get("content") or ""
            else:
                text = m
            text = re.sub(r"<[^>]+>", "", str(text))
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                lines.append(f"- {text}")
        lines.append("")
    return "\n".join(lines).strip()


async def _export(client: ZreadClient, repo: str, out_dir: str, concurrency: int) -> int:
    _, pages = await client.outline(repo)
    sem = asyncio.Semaphore(concurrency)

    async def one(p: Page):
        async with sem:
            md = await client.page(repo, p.slug)
            return p, md

    results = await asyncio.gather(*(one(p) for p in pages))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for p, md in results:
        fname = f"{p.slug}.md"
        (out / fname).write_text(md, encoding="utf-8")
        entries.append((p, fname))
    index = ["# " + repo, ""]
    for p, fname in entries:
        index.append(f"- [{p.topic}]({fname})")
    index_text = "\n".join(index) + "\n"
    (out / "llms.txt").write_text(index_text, encoding="utf-8")
    (out / "README.md").write_text(index_text, encoding="utf-8")
    full = "\n\n".join(f"# {p.topic}\n\n{md}" for p, md in results)
    (out / "llms-full.txt").write_text(full + "\n", encoding="utf-8")
    return len(entries)


@zread_app.command()
def structure(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language (zh|en)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Show the zread.ai table of contents for a repository."""
    resolved = _resolve_repo(repo, json)
    if (mock := _mock_text()) is not None:
        _emit(resolved, "structure", mock, False, json, content=mock)
        return
    client = _make_client(lang)
    try:
        with status("Fetching structure..."):
            _, pages = run_async(client.outline(resolved))
        text = _render_structure(pages)
    except Exception as exc:
        _handle_exception(exc, json)
    _emit(resolved, "structure", text, False, json, content=text)


@zread_app.command()
def contents(
    repo: str = typer.Argument(..., help="Repository (owner/repo, GitHub URL, or a blob URL with #L lines)"),
    slug: Optional[str] = typer.Argument(None, help="Page slug (default: overview)"),
    file: Optional[str] = typer.Option(None, "--file", help="Read a source file instead"),
    start: Optional[int] = typer.Option(None, "--start", help="Start line (with --file)"),
    end: Optional[int] = typer.Option(None, "--end", help="End line (with --file)"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language (zh|en)"),
    rich: bool = typer.Option(False, "--rich", help="Render Markdown with rich"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Show a single page of documentation (default: the overview page)."""
    raw_repo, embedded_file, embedded_start, embedded_end = _parse_repo_arg(repo)
    resolved = _resolve_repo(raw_repo, json)
    if file is None:
        file = embedded_file
    if start is None:
        start = embedded_start
    if end is None:
        end = embedded_end
    if slug is not None and file is not None:
        _fail("Specify either a slug or --file, not both.", "invalid_input", json)
    client = _make_client(lang)
    try:
        if file is not None:
            with status("Fetching file..."):
                info = run_async(client.repo_info(resolved))
                repo_id = str(info.get("repo_id") or "")
                if not repo_id:
                    raise ZreadNotFoundError(f"no repo_id for {resolved}")
                text = run_async(client.read_file(repo_id, file, start, end))
            _emit(resolved, "contents", text, False, json, content=text, file=file)
            return
        if (mock := _mock_text()) is not None:
            text = mock
        elif slug is None:
            with status("Fetching page..."):
                _, pages = run_async(client.outline(resolved))
                if not pages:
                    raise ZreadNotFoundError(f"no wiki pages for {resolved}")
                text = run_async(client.page(resolved, pages[0].slug))
        else:
            with status("Fetching page..."):
                text = run_async(client.page(resolved, slug))
    except Exception as exc:
        _handle_exception(exc, json)
    fields: dict[str, object] = {"content": text}
    if slug is not None:
        fields["slug"] = slug
    _emit(resolved, "contents", text, rich, json, **fields)


@zread_app.command()
def ask(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    question: Optional[str] = typer.Argument(None, help="Question (omit for interactive mode)"),
    model: Optional[str] = typer.Option(None, "--model", help="Model (glm-5.1|claude-sonnet-4.6)"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language (zh|en)"),
    rich: bool = typer.Option(False, "--rich", help="Render Markdown with rich"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    save: Optional[str] = typer.Option(None, "--save", help="Save the answer to a Markdown file."),
) -> None:
    """Ask a question about a repository (single-shot or interactive)."""
    resolved = _resolve_repo(repo, json)
    if question is not None:
        if not question.strip():
            _fail("Question must not be empty.", "invalid_input", json)
        if (mock := _mock_text()) is not None:
            answer = Answer(body=mock)
        else:
            client = _make_client(lang, model)
            try:
                with status("Thinking..."):
                    answer = Answer(body=run_async(client.ask(resolved, question)))
            except Exception as exc:
                _handle_exception(exc, json)
        if json:
            typer.echo(format_json(resolved, "ask", question=question, answer=answer.body))
        else:
            _emit(resolved, "ask", format_answer(answer), rich, False)
        _append_save(save, resolved, question, answer.body)
        return
    if json:
        typer.secho("Warning: --json has no effect in interactive mode.", fg=typer.colors.YELLOW, err=True)
    typer.echo(format_header("Zread", resolved, "ask"))
    typer.echo()
    typer.echo("Ask a question, or /exit to quit.")
    typer.echo()
    try:
        run_async(_repl(resolved, rich, save, model, lang))
    except Exception as exc:
        _handle_exception(exc, False)


@zread_app.command()
def find(
    query: str = typer.Argument(..., help="Search query"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Max results"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language (zh|en)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Search zread.ai for repositories."""
    client = _make_client(lang)
    try:
        with status("Searching..."):
            items = run_async(client.search_repos(query))
        if limit is not None:
            items = items[:limit]
    except Exception as exc:
        _handle_exception(exc, json)
    text = _format_repos(items)
    if json:
        typer.echo(format_json("", "find", results=items))
    else:
        typer.echo(format_result("Zread", query, "find", text))


@zread_app.command()
def search(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    query: str = typer.Argument(..., help="Text to search for inside the wiki"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language (zh|en)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Search within a repository's wiki documentation."""
    resolved = _resolve_repo(repo, json)
    client = _make_client(lang)
    try:
        with status("Searching..."):
            results = run_async(client.search_wiki(resolved, query))
    except Exception as exc:
        _handle_exception(exc, json)
    if json:
        typer.echo(format_json(resolved, "search", query=query, results=results))
    else:
        typer.echo(format_result("Zread", resolved, "search", _format_search(results)))


@zread_app.command()
def stat(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language (zh|en)"),
    human: bool = typer.Option(False, "--human", help="Show timestamps as human-readable times"),
    stale: bool = typer.Option(False, "--stale", help="Compare last_commit against GitHub HEAD"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Show repository info and index status on zread.ai."""
    resolved = _resolve_repo(repo, json)
    client = _make_client(lang)
    try:
        with status("Fetching status..."):
            data = run_async(client.repo_info(resolved))
        stale_info: dict | None = None
        if stale:
            last_commit = data.get("last_commit") if isinstance(data, dict) else None
            zread_sha = (last_commit or {}).get("hash") if isinstance(last_commit, dict) else None
            with status("Checking GitHub HEAD..."):
                head = run_async(client.github_head(resolved))
            stale_info = {
                "zread_sha": zread_sha or "",
                "github_sha": head.get("sha") or "",
                "github_when": head.get("when") or "",
            }
    except Exception as exc:
        _handle_exception(exc, json)
    if json:
        fields: dict[str, object] = {"data": data}
        if stale_info is not None:
            fields["stale"] = stale_info
        typer.echo(format_json(resolved, "stat", **fields))
    else:
        text = _format_stat(data, human)
        if stale_info is not None:
            text += "\n\n" + _format_stale(stale_info)
        typer.echo(format_result("Zread", resolved, "stat", text))


@zread_app.command()
def top(
    weeks: Optional[int] = typer.Argument(None, help="Number of week-groups to show"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language (zh|en)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Show the zread.ai trending list."""
    client = _make_client(lang)
    try:
        with status("Fetching trending..."):
            groups = run_async(client.trending())
        if weeks is not None:
            groups = groups[:weeks]
    except Exception as exc:
        _handle_exception(exc, json)
    if json:
        typer.echo(format_json("", "top", groups=groups))
    else:
        typer.echo(format_result("Zread", "", "top", _format_trending(groups)))


@zread_app.command()
def rand(
    topic: Optional[str] = typer.Argument(None, help="GitHub topic to filter by"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language (zh|en)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Get a random repository recommendation (optionally by topic)."""
    client = _make_client(lang)
    try:
        with status("Fetching recommendation..."):
            data = run_async(client.recommend(topic or ""))
    except Exception as exc:
        _handle_exception(exc, json)
    if json:
        typer.echo(format_json("", "rand", data=data))
    else:
        repos = data.get("repos", []) if isinstance(data, dict) else []
        text = _format_repos(repos)
        typer.echo(format_result("Zread", topic or "", "rand", text))


@zread_app.command()
def cp(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    output_dir: Optional[str] = typer.Argument(None, help="Output directory"),
    concurrency: int = typer.Option(5, "--concurrency", help="Parallel page fetches"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language (zh|en)"),
) -> None:
    """Export the whole wiki as Markdown files plus llms.txt."""
    if concurrency < 1:
        _fail("--concurrency must be at least 1", "invalid_input", False)
    resolved = _resolve_repo(repo, False)
    client = _make_client(lang)
    out = output_dir or resolved.replace("/", "_")
    try:
        with status("Exporting wiki..."):
            count = run_async(_export(client, resolved, out, concurrency))
    except Exception as exc:
        _handle_exception(exc, False)
    typer.echo(f"Exported {count} pages to {out}")


@zread_app.command()
def submit(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Submit a repository for indexing on zread.ai (requires ZREAD_TOKEN)."""
    resolved = _resolve_repo(repo, json)
    if not os.environ.get("ZREAD_TOKEN"):
        message = "ZREAD_TOKEN is not set; skipping submit. Set it to submit a repo for indexing."
        if json:
            typer.echo(format_error_json("missing_token", message), err=True)
        else:
            typer.secho(f"Warning: {message}", fg=typer.colors.YELLOW, err=True)
        return
    client = _make_client(None)
    try:
        with status("Submitting..."):
            data = run_async(client.submit(resolved))
    except Exception as exc:
        _handle_exception(exc, json)
    eta: dict = {}
    try:
        with status("Checking queue..."):
            eta = run_async(client.eta())
    except Exception:
        pass
    if json:
        typer.echo(format_json(resolved, "submit", data=data, eta=eta))
    else:
        message = f"Submitted {resolved} for indexing."
        if isinstance(eta, dict):
            backlog = eta.get("backlog")
            estimate = eta.get("estimate_minutes")
            if backlog is not None:
                message += f" Queue: {backlog} ahead"
                message += f" (~{estimate} min ETA)" if estimate is not None else "."
        typer.echo(message)


@zread_app.command()
def refresh(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Request a re-index (refresh) of a repository's wiki."""
    resolved = _resolve_repo(repo, json)
    client = _make_client(None)
    try:
        with status("Refreshing..."):
            data = run_async(client.refresh(resolved))
    except Exception as exc:
        _handle_exception(exc, json)
    if json:
        typer.echo(format_json(resolved, "refresh", data=data))
    else:
        typer.echo(f"Refreshed {resolved}.")

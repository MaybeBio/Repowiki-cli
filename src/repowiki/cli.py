"""CLI entry point for repowiki-cli."""

from __future__ import annotations

import os
import sys
from dataclasses import asdict
from typing import NoReturn, Optional

import typer
from typer.core import TyperCommand

from repowiki import __version__
from repowiki.client import (
    ConnectionError,
    DeepWikiClient,
    DeepWikiError,
    ToolError,
    run_async,
)
from repowiki.codemap import codemap_to_mermaid
from repowiki.devin import DevinClient
from repowiki.model import Answer
from repowiki.output import (
    filter_page,
    format_answer,
    format_command_json,
    format_error_json,
    format_header,
    format_json,
    format_list,
    format_result,
    format_status,
    format_warm,
    render_markdown,
    status,
)
from repowiki.repo import normalize_repo
from repowiki.save import append_entry, default_save_path

app = typer.Typer(add_completion=False)

# Sentinel injected into argv for a bare ``--save`` (no value). ``save`` then
# resolves to an auto-generated filename instead of an explicit path.
_SAVE_AUTO = "\x00auto\x00"


def _normalize_save(args: list[str]) -> list[str]:
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
                out.append(_SAVE_AUTO)
            else:
                out.append(args[i + 1])
                i += 1
        i += 1
    return out


class _AskCommand(TyperCommand):
    def parse_args(self, ctx, args):
        return super().parse_args(ctx, _normalize_save(args))


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"repowiki-cli {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    pass


def _error_message(exc: Exception) -> str:
    if isinstance(exc, ConnectionError):
        return "Could not connect to DeepWiki server. Check your connection and try again."
    if isinstance(exc, ToolError):
        return str(exc)
    if isinstance(exc, DeepWikiError):
        return str(exc)
    return f"Unexpected error: {exc}"


def _error_kind(exc: Exception) -> str:
    if isinstance(exc, ConnectionError):
        return "connection"
    if isinstance(exc, ToolError):
        message = str(exc).lower()
        if any(
            token in message
            for token in ("not indexed", "not_indexed", "not found", "to index")
        ):
            return "not_indexed"
        return "tool"
    if isinstance(exc, DeepWikiError):
        return "error"
    return "unexpected"


def _exit_code(kind: str) -> int:
    return {"not_indexed": 2, "connection": 3}.get(kind, 1)


def _fail(message: str, kind: str, json_mode: bool) -> NoReturn:
    """Print an error (JSON on stderr when requested) and exit."""
    if json_mode:
        typer.echo(format_error_json(kind, message), err=True)
    else:
        typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=_exit_code(kind))


def _print_error(exc: Exception) -> None:
    typer.secho(f"Error: {_error_message(exc)}", fg=typer.colors.RED, err=True)


def _handle_exception(exc: Exception, json_mode: bool = False) -> None:
    _fail(_error_message(exc), _error_kind(exc), json_mode)


def _resolve_repo(raw: str, json_mode: bool = False) -> str:
    try:
        return normalize_repo(raw)
    except ValueError as exc:
        _fail(str(exc), "invalid_repo", json_mode)


def _mock_text() -> Optional[str]:
    return os.environ.get("REPOWIKI_MOCK_TEXT")


def _repl_prompt() -> str:
    """Return the REPL input prompt, colored only on a terminal."""
    if not sys.stdout.isatty():
        return ">> "
    return typer.style(">> ", fg=typer.colors.CYAN, bold=True)


def _emit(
    repo: str,
    command: str,
    text: str,
    rich: bool,
    json_mode: bool = False,
    **json_fields: object,
) -> None:
    if json_mode:
        json_fields.setdefault("truncated", False)
        typer.echo(format_json(repo, command, **json_fields))
        return
    rendered = format_result(repo, command, text)
    if rich:
        render_markdown(rendered)
    else:
        typer.echo(rendered)


def _run_ask(
    repos: list[str],
    question: str,
    mode: str | None,
    query_id: str | None,
    use_devin: bool,
    context: str,
    generate_summary: bool,
) -> Answer:
    if use_devin:
        if (mock := os.environ.get("REPOWIKI_DEVIN_MOCK")) is not None:
            return Answer(body=mock)
        return run_async(
            DevinClient().ask(
                repos, question, mode=mode or "fast", query_id=query_id,
                context=context, generate_summary=generate_summary,
            )
        )
    if (mock := _mock_text()) is not None:
        return Answer(body=mock)
    return run_async(DeepWikiClient().ask_question(repos[0], question))


def _answer_json_fields(answer: Answer) -> dict[str, object]:
    fields: dict[str, object] = {
        "answer": answer.body,
        "truncated": answer.truncated,
    }
    if answer.summary:
        fields["summary"] = answer.summary
    if answer.references:
        fields["references"] = [asdict(r) for r in answer.references]
    if answer.sources:
        fields["sources"] = [asdict(s) for s in answer.sources]
    if answer.stats:
        fields["stats"] = answer.stats
    if answer.query_id:
        fields["query_id"] = answer.query_id
    return fields


def _emit_answer(
    repo: str,
    question: str,
    answer: Answer,
    rich: bool,
    json_mode: bool,
    show_sources: bool,
) -> None:
    if json_mode:
        fields = _answer_json_fields(answer)
        fields = {"question": question, **fields}
        typer.echo(format_json(repo, "ask", **fields))
        return
    _emit(repo, "ask", format_answer(answer, show_sources=show_sources), rich, False)


def _append_save(path: str | None, repo: str, question: str, answer: str) -> None:
    if path is None:
        return
    try:
        append_entry(path, repo, question, answer)
    except OSError as exc:
        typer.secho(
            f"Warning: could not save to {path}: {exc}",
            fg=typer.colors.YELLOW,
            err=True,
        )


async def _repl(resolved: str, rich: bool, save_path: str | None) -> None:
    prompt = _repl_prompt()
    async with DeepWikiClient() as client:
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
                    answer = await client.ask_question(resolved, q)
            except Exception as exc:
                _print_error(exc)
                continue
            _append_save(save_path, resolved, q, answer.body)
            typer.echo()
            if rich:
                render_markdown(answer.body.strip())
            else:
                typer.echo(answer.body.strip())
            typer.echo()


async def _repl_devin(
    repos: list[str],
    rich: bool,
    save_path: str | None,
    mode: str,
    initial_query_id: str | None,
    show_sources: bool,
    context: str,
    generate_summary: bool,
) -> None:
    prompt = _repl_prompt()
    devin = DevinClient()
    last_qid = initial_query_id
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
        if q == "/new":
            last_qid = None
            typer.echo("(started a new thread)")
            continue
        try:
            with status("Thinking..."):
                answer = await devin.ask(
                    repos, q, mode=mode, query_id=last_qid,
                    context=context, generate_summary=generate_summary,
                )
        except Exception as exc:
            _print_error(exc)
            continue
        last_qid = answer.query_id
        _append_save(save_path, repos[0], q, answer.body)
        typer.echo()
        rendered = format_answer(answer, show_sources=show_sources).strip()
        if rich:
            render_markdown(rendered)
        else:
            typer.echo(rendered)
        typer.echo()


@app.command()
def structure(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Show the documentation table of contents for a repository."""
    resolved = _resolve_repo(repo, json)
    if (mock := _mock_text()) is not None:
        _emit(resolved, "structure", mock, False, json, content=mock)
        return
    client = DeepWikiClient()
    try:
        with status("Fetching table of contents..."):
            text = run_async(client.read_wiki_structure(resolved))
    except Exception as exc:
        _handle_exception(exc, json)
    _emit(resolved, "structure", text, False, json, content=text)


@app.command()
def contents(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    page: Optional[str] = typer.Option(None, "--page", help="Show only the page with this title"),
    rich: bool = typer.Option(False, "--rich", help="Render Markdown with rich"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Show the full documentation for a repository."""
    resolved = _resolve_repo(repo, json)
    if (mock := _mock_text()) is not None:
        text = mock
    else:
        client = DeepWikiClient()
        try:
            with status("Fetching documentation..."):
                text = run_async(client.read_wiki_contents(resolved))
        except Exception as exc:
            _handle_exception(exc, json)
    if page is not None:
        try:
            text = filter_page(text, page)
        except ValueError as exc:
            _fail(str(exc), "page_not_found", json)
    fields: dict[str, object] = {"content": text}
    if page is not None:
        fields["page"] = page
    _emit(resolved, "contents", text, rich, json, **fields)


@app.command(cls=_AskCommand)
def ask(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    question: Optional[str] = typer.Argument(None, help="Question (omit for interactive mode)"),
    rich: bool = typer.Option(False, "--rich", help="Render Markdown with rich"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    save: Optional[str] = typer.Option(
        None,
        "--save",
        help="Save answers to a Markdown file. Bare --save auto-names the file; "
        "--save PATH writes/appends to PATH.",
    ),
    mode: Optional[str] = typer.Option(
        None, "--mode", help="Engine: fast, deep, or codemap (reverse backend)",
    ),
    query_id: Optional[str] = typer.Option(
        None, "--id", help="Continue a thread from a previous query id (reverse backend)",
    ),
    sources: bool = typer.Option(
        False, "--sources", help="Show source-code slices for citations (reverse backend)",
    ),
    no_summary: bool = typer.Option(
        False, "--no-summary", help="Skip summary generation (reverse backend)",
    ),
    context: Optional[str] = typer.Option(
        None, "--context", help="Additional context for the question (reverse backend)",
    ),
    extra_repos: Optional[list[str]] = typer.Option(
        None, "--repo", help="Additional repos to query (repeatable, reverse backend)",
    ),
    mermaid: bool = typer.Option(
        False, "--mermaid", help="Output a Mermaid diagram (codemap mode only)",
    ),
) -> None:
    """Ask a question about a repository (single-shot or interactive)."""
    resolved = _resolve_repo(repo, json)
    save_path = default_save_path(resolved) if save == _SAVE_AUTO else save

    if mode is not None and mode not in ("fast", "deep", "codemap"):
        _fail(f"Invalid --mode: {mode!r} (expected fast, deep, or codemap).", "invalid_input", json)
    all_repos = [resolved] + [_resolve_repo(r, json) for r in (extra_repos or [])]
    use_devin = bool(mode or query_id or sources or extra_repos
                     or (context is not None) or no_summary)
    generate_summary = not no_summary
    context_value = context or ""

    if question is not None:
        if not question.strip():
            _fail("Question must not be empty.", "invalid_input", json)
        try:
            with status("Thinking..."):
                answer = _run_ask(all_repos, question, mode, query_id, use_devin,
                                  context_value, generate_summary)
        except Exception as exc:
            _handle_exception(exc, json)
        if mermaid:
            mermaid_text = codemap_to_mermaid(answer.body)
            if mermaid_text is not None:
                if json:
                    fields: dict[str, object] = {"question": question, "mermaid": mermaid_text}
                    if answer.query_id:
                        fields["query_id"] = answer.query_id
                    typer.echo(format_json(resolved, "ask", **fields))
                else:
                    typer.echo(mermaid_text)
                _append_save(save_path, resolved, question, mermaid_text)
                return
            typer.secho(
                "Warning: --mermaid is set but the answer is not a codemap; showing as text.",
                fg=typer.colors.YELLOW,
                err=True,
            )
        _emit_answer(resolved, question, answer, rich, json, sources)
        _append_save(save_path, resolved, question, answer.body)
        return

    if json:
        typer.secho(
            "Warning: --json has no effect in interactive mode.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    typer.echo(format_header(resolved, "ask"))
    typer.echo()
    hint = "Ask a question, or /exit to quit."
    if use_devin:
        hint += "  (/new starts a new thread)"
    typer.echo(hint)
    typer.echo()
    try:
        if use_devin:
            run_async(_repl_devin(all_repos, rich, save_path, mode or "fast", query_id,
                                  sources, context_value, generate_summary))
        else:
            run_async(_repl(resolved, rich, save_path))
    except Exception as exc:
        _handle_exception(exc)


@app.command("list")
def list_indexes(
    search: str = typer.Argument(..., help="Search term for indexed repos"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Search DeepWiki's indexed public repositories."""
    client = DevinClient()
    try:
        with status("Searching..."):
            result = run_async(client.list_public_indexes(search))
    except Exception as exc:
        _handle_exception(exc, json)
    if json:
        typer.echo(format_command_json(
            "list", search=search,
            indices=result.get("indices") or [],
            needs_reindex=result.get("needs_reindex") or [],
            pending_repos=result.get("pending_repos") or [],
        ))
        return
    typer.echo(format_list(result))


# Named ``status_cmd`` (not ``status``) because the module-level ``status``
# spinner contextmanager from ``repowiki.output`` is referenced by every other
# command; a function named ``status`` would shadow it. The CLI name stays
# ``status`` via the explicit decorator argument, mirroring ``list``.
@app.command("status")
def status_cmd(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Check a repository's indexing status on DeepWiki."""
    resolved = _resolve_repo(repo, json)
    client = DevinClient()
    try:
        with status("Checking..."):
            result = run_async(client.public_repo_indexing_status(resolved))
    except Exception as exc:
        _handle_exception(exc, json)
    if json:
        typer.echo(format_command_json("status", repo=resolved, status=result.get("status") or "unknown"))
        return
    typer.echo(format_status(resolved, result))


@app.command()
def warm(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Pre-warm a repository's documentation cache on DeepWiki."""
    resolved = _resolve_repo(repo, json)
    client = DevinClient()
    try:
        with status("Warming..."):
            result = run_async(client.warm_public_repo(resolved))
    except Exception as exc:
        _handle_exception(exc, json)
    if json:
        typer.echo(format_command_json("warm", repo=resolved, status=result.get("status") or "OK"))
        return
    typer.echo(format_warm(resolved, result))


@app.command()
def get(
    query_id: str = typer.Argument(..., help="Query id to retrieve"),
    rich: bool = typer.Option(False, "--rich", help="Render Markdown with rich"),
    sources: bool = typer.Option(False, "--sources", help="Show source-code slices"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    mermaid: bool = typer.Option(
        False, "--mermaid", help="Output a Mermaid diagram (codemap queries only)",
    ),
) -> None:
    """Retrieve the result of a previous query by id."""
    client = DevinClient()
    try:
        with status("Fetching..."):
            answer = run_async(client.get_query(query_id))
    except Exception as exc:
        _handle_exception(exc, json)
    if mermaid:
        mermaid_text = codemap_to_mermaid(answer.body)
        if mermaid_text is not None:
            if json:
                fields: dict[str, object] = {"mermaid": mermaid_text}
                if answer.query_id:
                    fields["query_id"] = answer.query_id
                typer.echo(format_command_json("get", **fields))
            else:
                typer.echo(mermaid_text)
            return
        typer.secho(
            "Warning: --mermaid is set but the answer is not a codemap; showing as text.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    if json:
        typer.echo(format_command_json("get", **_answer_json_fields(answer)))
        return
    rendered = format_answer(answer, show_sources=sources)
    if rich:
        render_markdown(rendered)
    else:
        typer.echo(rendered)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

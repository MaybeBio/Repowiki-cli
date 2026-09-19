"""CLI commands for the CodeWiki service."""

from __future__ import annotations

import os
import sys
from typing import NoReturn, Optional

import typer

from repowiki.services.codewiki.client import (
    CodeWikiClient,
    CodeWikiConnectionError,
    CodeWikiError,
)
from repowiki.services.codewiki.wiki import render_markdown, render_page, render_structure
from repowiki.shared.async_ import run_async
from repowiki.shared.model import Answer
from repowiki.shared.output import (
    filter_page,
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

codewiki_app = typer.Typer(add_completion=False, help="Query Google Code Wiki documentation.")


def register(app: typer.Typer) -> None:
    """Mount the CodeWiki service commands on the root app."""
    app.add_typer(codewiki_app, name="codewiki")


def _mock_text() -> Optional[str]:
    return os.environ.get("REPOWIKI_CODEWIKI_MOCK") or None


def _resolve_repo(raw: str, json_mode: bool) -> str:
    try:
        return normalize_repo(raw)
    except ValueError as exc:
        _fail(str(exc), "invalid_repo", json_mode)


def _fail(message: str, kind: str, json_mode: bool) -> NoReturn:
    if json_mode:
        typer.echo(format_error_json(kind, message), err=True)
    else:
        typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code={"connection": 3}.get(kind, 1))


def _handle_exception(exc: Exception, json_mode: bool) -> NoReturn:
    if isinstance(exc, CodeWikiConnectionError):
        _fail(str(exc), "connection", json_mode)
    elif isinstance(exc, CodeWikiError):
        _fail(str(exc), "error", json_mode)
    _fail(f"Unexpected error: {exc}", "unexpected", json_mode)


def _emit(
    repo: str,
    command: str,
    text: str,
    rich: bool,
    json_mode: bool,
    **json_fields: object,
) -> None:
    if json_mode:
        typer.echo(format_json(repo, command, **json_fields))
        return
    rendered = format_result("CodeWiki", repo, command, text)
    if rich:
        render_rich(rendered)
    else:
        typer.echo(rendered)


def _repl_prompt() -> str:
    """Return the REPL input prompt, colored only on a terminal."""
    if not sys.stdout.isatty():
        return ">> "
    return typer.style(">> ", fg=typer.colors.CYAN, bold=True)


def _print_error(exc: Exception) -> None:
    if isinstance(exc, CodeWikiError):
        message = str(exc)
    else:
        message = f"Unexpected error: {exc}"
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)


def _append_save(
    path: Optional[str], repo: str, question: str, answer: str
) -> None:
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


async def _repl(resolved: str, rich: bool, save_path: Optional[str]) -> None:
    prompt = _repl_prompt()
    client = CodeWikiClient()
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


@codewiki_app.command()
def structure(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Show the CodeWiki table of contents for a repository."""
    resolved = _resolve_repo(repo, json)
    if (mock := _mock_text()) is not None:
        _emit(resolved, "structure", mock, False, json, content=mock)
        return
    client = CodeWikiClient()
    try:
        with status("Fetching table of contents..."):
            wiki = run_async(client.read_wiki(resolved))
        text = render_structure(wiki)
    except Exception as exc:
        _handle_exception(exc, json)
    _emit(resolved, "structure", text, False, json, content=text)


@codewiki_app.command()
def contents(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    page: Optional[str] = typer.Option(None, "--page", help="Show only the page with this title"),
    rich: bool = typer.Option(False, "--rich", help="Render Markdown with rich"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Show the full CodeWiki documentation for a repository."""
    resolved = _resolve_repo(repo, json)
    if (mock := _mock_text()) is not None:
        text = mock
        if page is not None:
            try:
                text = filter_page(text, page)
            except ValueError as exc:
                _fail(str(exc), "page_not_found", json)
    else:
        client = CodeWikiClient()
        try:
            with status("Fetching documentation..."):
                wiki = run_async(client.read_wiki(resolved))
        except Exception as exc:
            _handle_exception(exc, json)
        try:
            text = render_page(wiki, page) if page is not None else render_markdown(wiki)
        except ValueError as exc:
            _fail(str(exc), "page_not_found", json)
    fields: dict[str, object] = {"content": text}
    if page is not None:
        fields["page"] = page
    _emit(resolved, "contents", text, rich, json, **fields)


@codewiki_app.command()
def ask(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    question: Optional[str] = typer.Argument(
        None, help="Question (omit for interactive mode)"
    ),
    rich: bool = typer.Option(False, "--rich", help="Render Markdown with rich"),
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    save: Optional[str] = typer.Option(
        None, "--save", help="Save the answer to a Markdown file (appends)."
    ),
) -> None:
    """Ask a question about a repository (single-shot or interactive)."""
    resolved = _resolve_repo(repo, json)
    if question is not None:
        if not question.strip():
            _fail("Question must not be empty.", "invalid_input", json)
        if (mock := _mock_text()) is not None:
            answer = Answer(body=mock)
        else:
            client = CodeWikiClient()
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
        typer.secho(
            "Warning: --json has no effect in interactive mode.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    typer.echo(format_header("CodeWiki", resolved, "ask"))
    typer.echo()
    typer.echo("Ask a question, or /exit to quit.")
    typer.echo()
    try:
        run_async(_repl(resolved, rich, save))
    except Exception as exc:
        _handle_exception(exc, False)

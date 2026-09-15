"""CLI entry point for repowiki-cli."""

from __future__ import annotations

import os
from typing import Optional

import typer

from repowiki import __version__
from repowiki.client import (
    ConnectionError,
    DeepWikiClient,
    DeepWikiError,
    ToolError,
    run_async,
)
from repowiki.output import (
    filter_page,
    format_header,
    format_result,
    render_markdown,
)
from repowiki.repo import normalize_repo

app = typer.Typer(add_completion=False)


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


def _print_error(exc: Exception) -> None:
    typer.secho(f"Error: {_error_message(exc)}", fg=typer.colors.RED, err=True)


def _handle_exception(exc: Exception) -> None:
    _print_error(exc)
    raise typer.Exit(code=1)


def _resolve_repo(raw: str) -> str:
    try:
        return normalize_repo(raw)
    except ValueError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


def _mock_text() -> Optional[str]:
    return os.environ.get("REPOWIKI_MOCK_TEXT")


def _emit(repo: str, command: str, text: str, rich: bool) -> None:
    rendered = format_result(repo, command, text)
    if rich:
        render_markdown(rendered)
    else:
        typer.echo(rendered)


@app.command()
def structure(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
) -> None:
    """Show the documentation table of contents for a repository."""
    resolved = _resolve_repo(repo)
    if (mock := _mock_text()) is not None:
        typer.echo(format_result(resolved, "structure", mock))
        return
    client = DeepWikiClient()
    try:
        text = run_async(client.read_wiki_structure(resolved))
    except Exception as exc:
        _handle_exception(exc)
    typer.echo(format_result(resolved, "structure", text))


@app.command()
def contents(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    page: Optional[str] = typer.Option(None, "--page", help="Show only the page with this title"),
    rich: bool = typer.Option(False, "--rich", help="Render Markdown with rich"),
) -> None:
    """Show the full documentation for a repository."""
    resolved = _resolve_repo(repo)
    if (mock := _mock_text()) is not None:
        text = mock
    else:
        client = DeepWikiClient()
        try:
            text = run_async(client.read_wiki_contents(resolved))
        except Exception as exc:
            _handle_exception(exc)
    if page is not None:
        try:
            text = filter_page(text, page)
        except ValueError as exc:
            typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc
    _emit(resolved, "contents", text, rich)


@app.command()
def ask(
    repo: str = typer.Argument(..., help="Repository (owner/repo or GitHub URL)"),
    question: Optional[str] = typer.Argument(None, help="Question (omit for interactive mode)"),
    rich: bool = typer.Option(False, "--rich", help="Render Markdown with rich"),
) -> None:
    """Ask a question about a repository (single-shot or interactive)."""
    resolved = _resolve_repo(repo)

    if question is not None:
        if not question.strip():
            typer.secho("Error: Question must not be empty.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        if (mock := _mock_text()) is not None:
            _emit(resolved, "ask", mock, rich)
            return
        client = DeepWikiClient()
        try:
            text = run_async(client.ask_question(resolved, question))
        except Exception as exc:
            _handle_exception(exc)
        _emit(resolved, "ask", text, rich)
        return

    typer.echo(format_header(resolved, "ask"))
    typer.echo()
    typer.echo("Ask a question, or /exit to quit.")
    typer.echo()
    client = DeepWikiClient()
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            typer.echo()
            break
        q = line.strip()
        if not q:
            continue
        if q in ("/exit", "/quit", "/q"):
            break
        try:
            answer = run_async(client.ask_question(resolved, q))
        except Exception as exc:
            _print_error(exc)
            continue
        if rich:
            render_markdown(answer)
        else:
            typer.echo(answer)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

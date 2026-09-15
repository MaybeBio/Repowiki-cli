"""CLI entry point for repowiki-cli."""

from __future__ import annotations

import os
import sys
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
from repowiki.output import (
    filter_page,
    format_error_json,
    format_header,
    format_json,
    format_result,
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
) -> None:
    """Ask a question about a repository (single-shot or interactive)."""
    resolved = _resolve_repo(repo, json)
    save_path = default_save_path(resolved) if save == _SAVE_AUTO else save

    if question is not None:
        if not question.strip():
            _fail("Question must not be empty.", "invalid_input", json)
        if (mock := _mock_text()) is not None:
            _emit(resolved, "ask", mock, rich, json, question=question, answer=mock)
            _append_save(save_path, resolved, question, mock)
            return
        client = DeepWikiClient()
        try:
            with status("Thinking..."):
                answer = run_async(client.ask_question(resolved, question))
        except Exception as exc:
            _handle_exception(exc, json)
        _emit(resolved, "ask", answer.body, rich, json, question=question, answer=answer.body)
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
    typer.echo("Ask a question, or /exit to quit.")
    typer.echo()
    try:
        run_async(_repl(resolved, rich, save_path))
    except Exception as exc:
        _handle_exception(exc)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

"""CLI entry point for repowiki-cli."""

from __future__ import annotations

from typing import Optional

import typer

from repowiki import __version__
from repowiki.services.codewiki import register as register_codewiki
from repowiki.services.deepwiki import register as register_deepwiki

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


register_deepwiki(app)
register_codewiki(app)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

"""Root-level smoke tests for the composed CLI.

The root app only mounts one Typer sub-app per service; if a mount breaks, the
per-service test modules still pass because they import that service's app
directly. These tests walk in through the root namespace instead, so a service
that silently drops off the command surface is caught.

The version check exists because `__version__` was once hardcoded and drifted
from the packaged version. It is now derived from installed metadata, so a
mismatch here means either the metadata is stale (`uv sync`) or someone
re-introduced a hardcoded string.
"""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

import repowiki
from repowiki.cli import app

ROOT = Path(__file__).resolve().parent.parent
SERVICES = ("deepwiki", "codewiki", "zread")

runner = CliRunner()


def test_help_lists_every_service_namespace():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for service in SERVICES:
        assert service in result.output, f"{service} missing from root help"


@pytest.mark.parametrize("service", SERVICES)
def test_namespace_is_mounted_and_runnable(service):
    result = runner.invoke(app, [service, "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_version_matches_declared_package_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, "no version declared in pyproject.toml"
    declared = match.group(1)

    assert repowiki.__version__ == declared

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert declared in result.output

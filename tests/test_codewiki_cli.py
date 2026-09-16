from typer.testing import CliRunner

from repowiki.services.codewiki.cli import codewiki_app

runner = CliRunner()


def test_structure_mock(monkeypatch):
    monkeypatch.setenv("REPOWIKI_CODEWIKI_MOCK", "- Overview")
    result = runner.invoke(codewiki_app, ["structure", "facebook/react"])
    assert result.exit_code == 0
    assert "## CodeWiki: facebook/react (structure)" in result.output
    assert "- Overview" in result.output


def test_contents_mock(monkeypatch):
    monkeypatch.setenv("REPOWIKI_CODEWIKI_MOCK", "# Title\n\nbody")
    result = runner.invoke(codewiki_app, ["contents", "facebook/react"])
    assert result.exit_code == 0
    assert "## CodeWiki: facebook/react (contents)" in result.output
    assert "body" in result.output


def test_ask_mock(monkeypatch):
    monkeypatch.setenv("REPOWIKI_CODEWIKI_MOCK", "the answer")
    result = runner.invoke(codewiki_app, ["ask", "facebook/react", "how?"])
    assert result.exit_code == 0
    assert "the answer" in result.output


def test_invalid_repo_fails():
    result = runner.invoke(codewiki_app, ["structure", "not-a-repo"])
    assert result.exit_code != 0

from typer.testing import CliRunner

from repowiki.cli import app

runner = CliRunner()


def test_structure_command_mock(monkeypatch):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "1. Overview")
    result = runner.invoke(app, ["structure", "facebook/react"])
    assert result.exit_code == 0
    assert "## DeepWiki: facebook/react (structure)" in result.output
    assert "1. Overview" in result.output


def test_ask_single_shot_mock(monkeypatch):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "answer text")
    result = runner.invoke(app, ["ask", "facebook/react", "What is Fiber?"])
    assert result.exit_code == 0
    assert "## DeepWiki: facebook/react (ask)" in result.output
    assert "answer text" in result.output


def test_ask_accepts_url(monkeypatch):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "answer")
    result = runner.invoke(app, ["ask", "https://github.com/facebook/react", "q?"])
    assert result.exit_code == 0
    assert "## DeepWiki: facebook/react (ask)" in result.output


def test_invalid_repo():
    result = runner.invoke(app, ["structure", "facebook"])
    assert result.exit_code == 1
    assert "Error" in result.output


def test_empty_question_errors():
    result = runner.invoke(app, ["ask", "facebook/react", ""])
    assert result.exit_code == 1
    assert "Error" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "repowiki-cli" in result.output


def test_ask_repl(monkeypatch):
    inputs = iter(["What is Fiber?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    class FakeClient:
        async def ask_question(self, repo, question):
            return f"answer to {question}"

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FakeClient)
    result = runner.invoke(app, ["ask", "facebook/react"])
    assert result.exit_code == 0
    assert "answer to What is Fiber?" in result.output


def test_tool_error_returns_exit_1(monkeypatch):
    from repowiki.client import ToolError

    class FailingClient:
        async def read_wiki_structure(self, repo):
            raise ToolError("Tool 'read_wiki_structure' failed: boom")

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FailingClient)
    result = runner.invoke(app, ["structure", "facebook/react"])
    assert result.exit_code == 1
    assert "Error" in result.output


def test_connection_error_returns_exit_1(monkeypatch):
    from repowiki.client import ConnectionError

    class FailingClient:
        async def read_wiki_structure(self, repo):
            raise ConnectionError("Failed to connect to DeepWiki server")

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FailingClient)
    result = runner.invoke(app, ["structure", "facebook/react"])
    assert result.exit_code == 1
    assert "Could not connect" in result.output

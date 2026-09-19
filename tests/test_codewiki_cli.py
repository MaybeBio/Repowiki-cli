from pathlib import Path

from typer.testing import CliRunner

from repowiki.cli import app as root_app
from repowiki.services.codewiki.boq import decode_response
from repowiki.services.codewiki.cli import codewiki_app
from repowiki.services.codewiki.wiki import parse

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "codewiki"


def _fixture_wiki():
    body = (FIXTURES / "vsx6ub_response.txt").read_text(encoding="utf-8")
    return parse(decode_response(body, "VSX6ub"))


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


def test_root_mount_lists_codewiki_commands(monkeypatch):
    monkeypatch.setenv("REPOWIKI_CODEWIKI_MOCK", "- Overview")
    result = runner.invoke(root_app, ["codewiki", "structure", "facebook/react"])
    assert result.exit_code == 0
    assert "## CodeWiki: facebook/react (structure)" in result.output


def test_contents_page_filters_section(monkeypatch):
    wiki = _fixture_wiki()

    class FakeClient:
        async def read_wiki(self, repo):
            return wiki

    monkeypatch.setattr("repowiki.services.codewiki.cli.CodeWikiClient", FakeClient)
    result = runner.invoke(codewiki_app, ["contents", "owner/example", "--page", "Section A"])
    assert result.exit_code == 0
    assert "## Section A" in result.output
    assert "Example Overview" not in result.output


def test_ask_repl(monkeypatch):
    inputs = iter(["What is Fiber?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    class FakeClient:
        async def ask(self, repo, question):
            return f"answer to {question}"

    monkeypatch.setattr("repowiki.services.codewiki.cli.CodeWikiClient", FakeClient)
    result = runner.invoke(codewiki_app, ["ask", "facebook/react"])
    assert result.exit_code == 0
    assert "answer to What is Fiber?" in result.output


def test_ask_repl_uses_prompt(monkeypatch):
    prompts = []
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": prompts.append(prompt) or "/exit"
    )

    class FakeClient:
        async def ask(self, repo, question):
            return "answer"

    monkeypatch.setattr("repowiki.services.codewiki.cli.CodeWikiClient", FakeClient)
    result = runner.invoke(codewiki_app, ["ask", "facebook/react"])
    assert result.exit_code == 0
    assert prompts == [">> "]


def test_ask_repl_warns_json(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "/exit")

    class FakeClient:
        async def ask(self, repo, question):
            return "answer"

    monkeypatch.setattr("repowiki.services.codewiki.cli.CodeWikiClient", FakeClient)
    result = runner.invoke(codewiki_app, ["ask", "facebook/react", "--json"])
    assert result.exit_code == 0
    assert "--json has no effect in interactive mode" in result.output


def test_ask_empty_question_fails(monkeypatch):
    monkeypatch.setenv("REPOWIKI_CODEWIKI_MOCK", "the answer")
    result = runner.invoke(codewiki_app, ["ask", "facebook/react", ""])
    assert result.exit_code != 0

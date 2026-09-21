import json
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


def test_stat_command(monkeypatch):
    wiki = _fixture_wiki()

    class FakeClient:
        async def read_wiki(self, repo):
            return wiki

    monkeypatch.setattr("repowiki.services.codewiki.cli.CodeWikiClient", FakeClient)
    result = runner.invoke(codewiki_app, ["stat", "owner/example"])
    assert result.exit_code == 0
    assert "commit: abc123" in result.output


def test_stat_stale_up_to_date(monkeypatch):
    wiki = _fixture_wiki()

    class FakeClient:
        async def read_wiki(self, repo):
            return wiki

        async def github_head(self, repo):
            return {"sha": "abc123456789", "when": "2026-08-07T05:46:59Z"}

    monkeypatch.setattr("repowiki.services.codewiki.cli.CodeWikiClient", FakeClient)
    result = runner.invoke(codewiki_app, ["stat", "owner/example", "--stale"])
    assert result.exit_code == 0
    assert "最新" in result.output


def test_stat_stale_mismatch(monkeypatch):
    wiki = _fixture_wiki()

    class FakeClient:
        async def read_wiki(self, repo):
            return wiki

        async def github_head(self, repo):
            return {"sha": "0dcbe194ab8759", "when": "2026-08-07T05:46:59Z"}

    monkeypatch.setattr("repowiki.services.codewiki.cli.CodeWikiClient", FakeClient)
    result = runner.invoke(codewiki_app, ["stat", "owner/example", "--stale"])
    assert result.exit_code == 0
    assert "过期" in result.output


def test_stat_stale_json(monkeypatch):
    wiki = _fixture_wiki()

    class FakeClient:
        async def read_wiki(self, repo):
            return wiki

        async def github_head(self, repo):
            return {"sha": "abc123456789", "when": "2026-08-07T05:46:59Z"}

    monkeypatch.setattr("repowiki.services.codewiki.cli.CodeWikiClient", FakeClient)
    result = runner.invoke(codewiki_app, ["stat", "owner/example", "--stale", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["repo"] == "owner/example"
    assert data["command"] == "stat"
    assert data["commit"] == "abc123"
    assert data["stale"]["wiki_sha"] == "abc123"
    assert data["stale"]["github_sha"] == "abc123456789"


def test_cp_exports_pages(monkeypatch, tmp_path):
    wiki = _fixture_wiki()

    class FakeClient:
        async def read_wiki(self, repo):
            return wiki

    monkeypatch.setattr("repowiki.services.codewiki.cli.CodeWikiClient", FakeClient)
    out = tmp_path / "export"
    result = runner.invoke(codewiki_app, ["cp", "owner/example", str(out)])
    assert result.exit_code == 0
    assert (out / "llms.txt").exists()
    assert (out / "llms-full.txt").exists()
    assert (out / "README.md").exists()
    pages = [p.name for p in out.iterdir() if p.suffix == ".md" and p.name != "README.md"]
    assert len(pages) == 3
    assert "Exported 3 pages" in result.output


def test_cp_default_output_dir(monkeypatch, tmp_path):
    wiki = _fixture_wiki()

    class FakeClient:
        async def read_wiki(self, repo):
            return wiki

    monkeypatch.setattr("repowiki.services.codewiki.cli.CodeWikiClient", FakeClient)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(codewiki_app, ["cp", "owner/example"])
    assert result.exit_code == 0
    assert (tmp_path / "owner_example" / "llms.txt").exists()


def test_ask_save_bare_auto_names(monkeypatch, tmp_path):
    monkeypatch.setenv("REPOWIKI_CODEWIKI_MOCK", "the answer")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(codewiki_app, ["ask", "owner/example", "q?", "--save"])
    assert result.exit_code == 0
    files = list(tmp_path.glob("repowiki-owner-example_*.md"))
    assert len(files) == 1
    assert "the answer" in files[0].read_text()

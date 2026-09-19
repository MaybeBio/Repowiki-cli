from pathlib import Path

from typer.testing import CliRunner

from repowiki.cli import app as root_app
from repowiki.services.zread.cli import zread_app

runner = CliRunner()


def test_structure_mock(monkeypatch):
    monkeypatch.setenv("REPOWIKI_ZREAD_MOCK", "- Overview")
    result = runner.invoke(zread_app, ["structure", "facebook/react"])
    assert result.exit_code == 0
    assert "## Zread: facebook/react (structure)" in result.output
    assert "- Overview" in result.output


def test_contents_mock(monkeypatch):
    monkeypatch.setenv("REPOWIKI_ZREAD_MOCK", "# Title\n\nbody")
    result = runner.invoke(zread_app, ["contents", "facebook/react"])
    assert result.exit_code == 0
    assert "body" in result.output


def test_ask_mock(monkeypatch):
    monkeypatch.setenv("REPOWIKI_ZREAD_MOCK", "the answer")
    result = runner.invoke(zread_app, ["ask", "facebook/react", "how?"])
    assert result.exit_code == 0
    assert "the answer" in result.output


def test_invalid_repo_fails():
    result = runner.invoke(zread_app, ["structure", "not-a-repo"])
    assert result.exit_code != 0


def test_root_mount_lists_zread_commands(monkeypatch):
    monkeypatch.setenv("REPOWIKI_ZREAD_MOCK", "- Overview")
    result = runner.invoke(root_app, ["zread", "structure", "facebook/react"])
    assert result.exit_code == 0
    assert "## Zread: facebook/react (structure)" in result.output


def test_contents_no_slug_defaults_to_overview(monkeypatch):
    from repowiki.services.zread.flight import Page

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def outline(self, repo):
            return None, [Page("p0", "overview", "Overview", order=0)]

        async def page(self, repo, slug=None):
            return "# Overview\n\nbody"

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["contents", "owner/example"])
    assert result.exit_code == 0
    assert "# Overview" in result.output


def test_contents_file_uses_read_file(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def repo_info(self, repo):
            return {"repo_id": "r1"}

        async def read_file(self, repo_id, path, start=None, end=None):
            return f"content of {path}"

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["contents", "owner/example", "--file", "src/main.py"])
    assert result.exit_code == 0
    assert "content of src/main.py" in result.output


def test_find_json(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def search_repos(self, query):
            return [{"name": "foo/bar"}]

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["find", "react", "--json"])
    assert result.exit_code == 0
    assert '"command": "find"' in result.output
    assert "foo/bar" in result.output


def test_ask_repl(monkeypatch):
    inputs = iter(["What is Fiber?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def ask(self, repo, question):
            return f"answer to {question}"

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["ask", "facebook/react"])
    assert result.exit_code == 0
    assert "answer to What is Fiber?" in result.output


def test_cp_concurrency_zero_fails(monkeypatch):
    monkeypatch.setenv("REPOWIKI_ZREAD_MOCK", "- Overview")
    result = runner.invoke(zread_app, ["cp", "owner/example", "--concurrency", "0"])
    assert result.exit_code == 1
    assert "--concurrency must be at least 1" in result.output


def test_cp_writes_files(monkeypatch, tmp_path):
    from repowiki.services.zread.flight import Page

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def outline(self, repo):
            return None, [Page("p0", "a", "A", order=0), Page("p1", "b", "B", order=1)]

        async def page(self, repo, slug=None):
            return f"# {slug} body"

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["cp", "owner/example", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "00-a.md").exists()
    assert (tmp_path / "llms.txt").exists()
    assert (tmp_path / "llms-full.txt").exists()

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


def test_parse_repo_arg_blob_url():
    from repowiki.services.zread.cli import _parse_repo_arg

    ref, path, start, end = _parse_repo_arg(
        "https://github.com/owner/example/blob/main/src/a.py#L10-L20"
    )
    assert ref == "https://github.com/owner/example"
    assert path == "src/a.py"
    assert (start, end) == (10, 20)


def test_parse_repo_arg_single_line_fragment():
    from repowiki.services.zread.cli import _parse_repo_arg

    ref, path, start, end = _parse_repo_arg("github.com/owner/example/blob/main/a.py#L10")
    assert ref == "github.com/owner/example"
    assert path == "a.py"
    assert (start, end) == (10, None)


def test_parse_repo_arg_plain_repo():
    from repowiki.services.zread.cli import _parse_repo_arg

    ref, path, start, end = _parse_repo_arg("owner/example")
    assert ref == "owner/example"
    assert path is None
    assert (start, end) == (None, None)


def test_contents_blob_url_parses_file_and_lines(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def repo_info(self, repo):
            seen["repo"] = repo
            return {"repo_id": "r1"}

        async def read_file(self, repo_id, path, start=None, end=None):
            seen["path"] = path
            seen["start"] = start
            seen["end"] = end
            return f"content of {path}"

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(
        zread_app,
        ["contents", "github.com/owner/example/blob/main/src/main.py#L10-L20"],
    )
    assert result.exit_code == 0
    assert seen["repo"] == "owner/example"
    assert seen["path"] == "src/main.py"
    assert seen["start"] == 10
    assert seen["end"] == 20
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
    assert (tmp_path / "a.md").exists()
    assert (tmp_path / "llms.txt").exists()
    assert (tmp_path / "llms-full.txt").exists()
    assert (tmp_path / "README.md").exists()


def test_submit_skips_without_token(monkeypatch):
    monkeypatch.delenv("ZREAD_TOKEN", raising=False)
    result = runner.invoke(zread_app, ["submit", "owner/example"])
    assert result.exit_code == 0
    assert "ZREAD_TOKEN is not set" in result.output


def test_submit_with_token(monkeypatch):
    monkeypatch.setenv("ZREAD_TOKEN", "tok")

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def submit(self, repo):
            return {"ok": True}

        async def eta(self):
            return {"backlog": 6, "estimate_minutes": 34}

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["submit", "owner/example"])
    assert result.exit_code == 0
    assert "Submitted owner/example" in result.output
    assert "6 ahead" in result.output
    assert "34 min" in result.output


def test_submit_json_includes_eta(monkeypatch):
    monkeypatch.setenv("ZREAD_TOKEN", "tok")

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def submit(self, repo):
            return {"ok": True}

        async def eta(self):
            return {"backlog": 6, "estimate_minutes": 34}

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["submit", "owner/example", "--json"])
    assert result.exit_code == 0
    assert '"command": "submit"' in result.output
    assert '"backlog": 6' in result.output


def test_search_command(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def search_wiki(self, repo, query):
            return [{"title": "Overview", "slug": "1-overview", "matches": [{"highlight": "<em>fiber</em> here"}]}]

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["search", "owner/example", "fiber"])
    assert result.exit_code == 0
    assert "Overview" in result.output
    assert "fiber" in result.output


def test_search_json(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def search_wiki(self, repo, query):
            return [{"title": "T", "slug": "s", "matches": []}]

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["search", "owner/example", "q", "--json"])
    assert result.exit_code == 0
    assert '"command": "search"' in result.output


def test_refresh_command(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def refresh(self, repo):
            return {"repo_id": "r1", "ok": True}

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["refresh", "owner/example"])
    assert result.exit_code == 0
    assert "Refreshed owner/example" in result.output


def test_refresh_json(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def refresh(self, repo):
            return {"repo_id": "r1", "ok": True}

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["refresh", "owner/example", "--json"])
    assert result.exit_code == 0
    assert '"command": "refresh"' in result.output


def test_stat_human_formats_timestamps(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def repo_info(self, repo):
            return {
                "created_at": 1753248298,
                "updated_at": 1775500995,
                "last_commit": {"hash": "abc123", "when": 1775043592},
            }

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["stat", "owner/example", "--human"])
    assert result.exit_code == 0
    assert "2025-07-23" in result.output
    assert "2026-04-01" in result.output


def test_stat_stale_up_to_date(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def repo_info(self, repo):
            return {"last_commit": {"hash": "abc123", "when": 1775043592}}

        async def github_head(self, repo):
            return {"sha": "abc123", "when": "2026-08-19T10:00:00Z"}

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["stat", "owner/example", "--stale"])
    assert result.exit_code == 0
    assert "最新" in result.output


def test_stat_stale_mismatch(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def repo_info(self, repo):
            return {"last_commit": {"hash": "abc123", "when": 1775043592}}

        async def github_head(self, repo):
            return {"sha": "def456", "when": "2026-08-19T10:00:00Z"}

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["stat", "owner/example", "--stale"])
    assert result.exit_code == 0
    assert "过期" in result.output


def test_stat_stale_json(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def repo_info(self, repo):
            return {"last_commit": {"hash": "abc123", "when": 1775043592}}

        async def github_head(self, repo):
            return {"sha": "def456", "when": "2026-08-19T10:00:00Z"}

    monkeypatch.setattr("repowiki.services.zread.cli.ZreadClient", FakeClient)
    result = runner.invoke(zread_app, ["stat", "owner/example", "--stale", "--json"])
    assert result.exit_code == 0
    assert '"stale"' in result.output
    assert '"github_sha": "def456"' in result.output

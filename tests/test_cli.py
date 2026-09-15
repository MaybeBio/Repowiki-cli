import json

from typer.testing import CliRunner

from repowiki.cli import app
from repowiki.model import Answer, Reference, SourceFile

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
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def ask_question(self, repo, question):
            return Answer(body=f"answer to {question}")

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FakeClient)
    result = runner.invoke(app, ["ask", "facebook/react"])
    assert result.exit_code == 0
    assert "answer to What is Fiber?" in result.output


def test_ask_repl_uses_prominent_marker(monkeypatch):
    prompts = []
    inputs = iter(["What is Fiber?", "/exit"])

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def ask_question(self, repo, question):
            return Answer(body=f"answer to {question}")

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FakeClient)
    result = runner.invoke(app, ["ask", "facebook/react"])
    assert result.exit_code == 0
    assert prompts
    assert all(">>" in p for p in prompts)


def test_tool_error_returns_exit_1(monkeypatch):
    from repowiki.client import ToolError

    class FailingClient:
        async def read_wiki_structure(self, repo):
            raise ToolError("Tool 'read_wiki_structure' failed: boom")

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FailingClient)
    result = runner.invoke(app, ["structure", "facebook/react"])
    assert result.exit_code == 1
    assert "Error" in result.output


def test_connection_error_returns_exit_3(monkeypatch):
    from repowiki.client import ConnectionError

    class FailingClient:
        async def read_wiki_structure(self, repo):
            raise ConnectionError("Failed to connect to DeepWiki server")

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FailingClient)
    result = runner.invoke(app, ["structure", "facebook/react"])
    assert result.exit_code == 3
    assert "Could not connect" in result.output


def test_not_indexed_returns_exit_2(monkeypatch):
    from repowiki.client import ToolError

    class FailingClient:
        async def read_wiki_structure(self, repo):
            raise ToolError("Tool 'read_wiki_structure' failed: repo not indexed")

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FailingClient)
    result = runner.invoke(app, ["structure", "facebook/react"])
    assert result.exit_code == 2
    assert "not indexed" in result.output


def test_not_indexed_real_deepwiki_phrasing(monkeypatch):
    from repowiki.client import ToolError

    class FailingClient:
        async def read_wiki_structure(self, repo):
            raise ToolError(
                "Error processing question: Repository not found. "
                "Visit https://deepwiki.com to index it. "
                "Requested repos: MaybeBio/pyPaperFlow"
            )

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FailingClient)
    result = runner.invoke(app, ["structure", "MaybeBio/pyPaperFlow", "--json"])
    assert result.exit_code == 2
    data = json.loads(result.output)
    assert data["kind"] == "not_indexed"


def test_contents_page_filter_mock(monkeypatch):
    sample = "# Page: Overview\n\n# Overview\n\nbody\n\n# Page: Other\n\n# Other\n\nother body"
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", sample)
    result = runner.invoke(app, ["contents", "facebook/react", "--page", "Overview"])
    assert result.exit_code == 0
    assert "## DeepWiki: facebook/react (contents)" in result.output
    assert "body" in result.output
    assert "other body" not in result.output


def test_contents_page_not_found(monkeypatch):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "# Page: Overview\n\n# Overview\n\nbody")
    result = runner.invoke(app, ["contents", "facebook/react", "--page", "Missing"])
    assert result.exit_code == 1
    assert "Error" in result.output
    assert "Overview" in result.output


def test_contents_rich_mock(monkeypatch):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "# Hello\n\nsome **bold** text")
    result = runner.invoke(app, ["contents", "facebook/react", "--rich"])
    assert result.exit_code == 0
    assert "Hello" in result.output
    assert "bold" in result.output


def test_ask_rich_mock(monkeypatch):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "# Answer\n\nsome text")
    result = runner.invoke(app, ["ask", "facebook/react", "q?", "--rich"])
    assert result.exit_code == 0
    assert "Answer" in result.output


def test_ask_save_explicit_path(monkeypatch, tmp_path):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "the answer")
    out = tmp_path / "qa.md"
    result = runner.invoke(
        app, ["ask", "facebook/react", "what is fiber?", "--save", str(out)]
    )
    assert result.exit_code == 0
    text = out.read_text()
    assert "**Q:** what is fiber?" in text
    assert "the answer" in text


def test_ask_save_bare_auto_names(monkeypatch, tmp_path):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "the answer")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["ask", "facebook/react", "what is fiber?", "--save"])
    assert result.exit_code == 0
    files = list(tmp_path.glob("repowiki-facebook-react_*.md"))
    assert len(files) == 1
    assert "the answer" in files[0].read_text()


def test_structure_json(monkeypatch):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "1. Overview")
    result = runner.invoke(app, ["structure", "facebook/react", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "repo": "facebook/react",
        "command": "structure",
        "content": "1. Overview",
        "truncated": False,
    }


def test_ask_single_shot_json(monkeypatch):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "answer text")
    result = runner.invoke(app, ["ask", "facebook/react", "What is Fiber?", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "repo": "facebook/react",
        "command": "ask",
        "question": "What is Fiber?",
        "answer": "answer text",
        "truncated": False,
    }


def test_contents_json_with_page(monkeypatch):
    sample = "# Page: Overview\n\n# Overview\n\nbody\n\n# Page: Other\n\n# Other\n\nother body"
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", sample)
    result = runner.invoke(
        app, ["contents", "facebook/react", "--page", "Overview", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["command"] == "contents"
    assert data["page"] == "Overview"
    assert "body" in data["content"]
    assert "other body" not in data["content"]
    assert data["truncated"] is False


def test_error_json_connection(monkeypatch):
    from repowiki.client import ConnectionError

    class FailingClient:
        async def read_wiki_structure(self, repo):
            raise ConnectionError("Failed to connect to DeepWiki server")

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FailingClient)
    result = runner.invoke(app, ["structure", "facebook/react", "--json"])
    assert result.exit_code == 3
    data = json.loads(result.output)
    assert data["kind"] == "connection"
    assert "connect" in data["error"].lower()


def test_error_json_not_indexed(monkeypatch):
    from repowiki.client import ToolError

    class FailingClient:
        async def read_wiki_structure(self, repo):
            raise ToolError("Tool 'read_wiki_structure' failed: repo not indexed")

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FailingClient)
    result = runner.invoke(app, ["structure", "facebook/react", "--json"])
    assert result.exit_code == 2
    data = json.loads(result.output)
    assert data["kind"] == "not_indexed"


def test_invalid_repo_json():
    result = runner.invoke(app, ["structure", "facebook", "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["kind"] == "invalid_repo"


def test_ask_mode_routes_to_devin(monkeypatch):
    captured = {}

    class FakeDevin:
        async def ask(self, repos, question, *, mode="fast", query_id=None, context="", generate_summary=True):
            captured.update(repo=repos[0], question=question, mode=mode, query_id=query_id)
            return Answer(body="devin answer", query_id="q1")

    monkeypatch.setattr("repowiki.cli.DevinClient", FakeDevin)
    result = runner.invoke(app, ["ask", "facebook/react", "q?", "--mode", "deep"])
    assert result.exit_code == 0
    assert captured["mode"] == "deep"
    assert "devin answer" in result.output


def test_ask_repo_flag_routes_to_devin_and_multi_repo(monkeypatch):
    captured = {}

    class FakeDevin:
        async def ask(self, repos, question, *, mode="fast", query_id=None, context="", generate_summary=True):
            captured["repos"] = repos
            return Answer(body="multi answer", query_id="q1")

    monkeypatch.setattr("repowiki.cli.DevinClient", FakeDevin)
    result = runner.invoke(
        app,
        ["ask", "facebook/react", "diff?", "--repo", "remix-run/react-router", "--repo", "TanStack/router"],
    )
    assert result.exit_code == 0
    assert captured["repos"] == ["facebook/react", "remix-run/react-router", "TanStack/router"]
    assert "multi answer" in result.output


def test_ask_context_and_no_summary_route_to_devin(monkeypatch):
    captured = {}

    class FakeDevin:
        async def ask(self, repos, question, *, mode="fast", query_id=None, context="", generate_summary=True):
            captured.update(context=context, generate_summary=generate_summary)
            return Answer(body="ok")

    monkeypatch.setattr("repowiki.cli.DevinClient", FakeDevin)
    result = runner.invoke(app, ["ask", "facebook/react", "q?", "--context", "in Chinese", "--no-summary"])
    assert result.exit_code == 0
    assert captured == {"context": "in Chinese", "generate_summary": False}


def test_ask_no_flags_still_mcp(monkeypatch):
    monkeypatch.setenv("REPOWIKI_MOCK_TEXT", "mcp answer")
    result = runner.invoke(app, ["ask", "facebook/react", "q?"])
    assert result.exit_code == 0
    assert "mcp answer" in result.output


def test_ask_devin_json(monkeypatch):
    class FakeDevin:
        async def ask(self, repos, question, *, mode="fast", query_id=None, context="", generate_summary=True):
            return Answer(
                body="devin answer",
                summary="sum",
                references=[Reference("f.py", 1, 2)],
                query_id="q1",
            )

    monkeypatch.setattr("repowiki.cli.DevinClient", FakeDevin)
    result = runner.invoke(app, ["ask", "facebook/react", "q?", "--mode", "deep", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["query_id"] == "q1"
    assert data["summary"] == "sum"
    assert data["references"] == [{"file_path": "f.py", "range_start": 1, "range_end": 2}]


def test_ask_invalid_mode(monkeypatch):
    result = runner.invoke(app, ["ask", "facebook/react", "q?", "--mode", "bogus"])
    assert result.exit_code == 1
    assert "Error" in result.output


def test_ask_devin_unindexed_exit_2(monkeypatch):
    from repowiki.client import ToolError

    class FailingDevin:
        async def ask(self, repos, question, *, mode="fast", query_id=None, context="", generate_summary=True):
            raise ToolError("Devin API returned HTTP 400: Repos not found")

    monkeypatch.setattr("repowiki.cli.DevinClient", FailingDevin)
    result = runner.invoke(app, ["ask", "facebook/react", "q?", "--mode", "deep"])
    assert result.exit_code == 2
    assert "Repos not found" in result.output


def test_ask_sources_renders_slices(monkeypatch):
    class FakeDevin:
        async def ask(self, repos, question, *, mode="fast", query_id=None, context="", generate_summary=True):
            return Answer(
                body="body .",
                references=[Reference("f.py", 1, 2)],
                sources=[SourceFile("a/b", "f.py", "l1\nl2\nl3")],
            )

    monkeypatch.setattr("repowiki.cli.DevinClient", FakeDevin)
    result = runner.invoke(app, ["ask", "facebook/react", "q?", "--mode", "deep", "--sources"])
    assert result.exit_code == 0
    assert "Sources" in result.output
    assert "f.py:1-2" in result.output
    assert "l1" in result.output


def test_ask_repl_devin_auto_threads(monkeypatch):
    inputs = iter(["first", "second", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    seen_qids = []

    class FakeDevin:
        async def ask(self, repos, question, *, mode="fast", query_id=None, context="", generate_summary=True):
            seen_qids.append(query_id)
            return Answer(body=f"answer to {question}", query_id=f"qid-{question}")

    monkeypatch.setattr("repowiki.cli.DevinClient", FakeDevin)
    result = runner.invoke(app, ["ask", "facebook/react", "--mode", "deep"])
    assert result.exit_code == 0
    assert seen_qids == [None, "qid-first"]
    assert "answer to first" in result.output
    assert "answer to second" in result.output


def test_ask_repl_devin_new_resets_thread(monkeypatch):
    inputs = iter(["first", "/new", "second", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    seen_qids = []

    class FakeDevin:
        async def ask(self, repos, question, *, mode="fast", query_id=None, context="", generate_summary=True):
            seen_qids.append(query_id)
            return Answer(body=f"answer to {question}", query_id=f"qid-{question}")

    monkeypatch.setattr("repowiki.cli.DevinClient", FakeDevin)
    result = runner.invoke(app, ["ask", "facebook/react", "--mode", "deep"])
    assert result.exit_code == 0
    assert seen_qids == [None, None]


def test_ask_save_repl_appends(monkeypatch, tmp_path):
    inputs = iter(["What is Fiber?", "What are hooks?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def ask_question(self, repo, question):
            return Answer(body=f"answer to {question}")

    monkeypatch.setattr("repowiki.cli.DeepWikiClient", FakeClient)
    out = tmp_path / "qa.md"
    result = runner.invoke(app, ["ask", "facebook/react", "--save", str(out)])
    assert result.exit_code == 0
    text = out.read_text()
    assert text.count("**Q:**") == 2
    assert "answer to What is Fiber?" in text
    assert "answer to What are hooks?" in text

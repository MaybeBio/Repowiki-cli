import io

import pytest

from repowiki.model import Answer, Reference, SourceFile
from repowiki.output import (
    _prepare_markdown,
    filter_page,
    format_answer,
    format_header,
    format_result,
    list_page_titles,
    status,
)


def test_format_header():
    assert format_header("facebook/react", "ask") == "## DeepWiki: facebook/react (ask)"


def test_format_result_adds_header_and_trims():
    result = format_result("facebook/react", "ask", "  some content  \n")
    assert result == "## DeepWiki: facebook/react (ask)\n\nsome content"


def test_format_result_empty_text():
    result = format_result("owner/repo", "contents", "   \n\t  ")
    assert result == "## DeepWiki: owner/repo (contents)\n\n"


SAMPLE = "# Page: Overview\n\n# Overview\n\noverview body\n\n# Page: Getting Started\n\n# Getting Started\n\nstart body\n"


def test_list_page_titles():
    assert list_page_titles(SAMPLE) == ["Overview", "Getting Started"]


def test_filter_page_exact():
    result = filter_page(SAMPLE, "Overview")
    assert result.startswith("# Overview")
    assert "overview body" in result
    assert "start body" not in result


def test_filter_page_case_insensitive():
    result = filter_page(SAMPLE, "overview")
    assert "overview body" in result


def test_filter_page_not_found_lists_titles():
    with pytest.raises(ValueError) as exc:
        filter_page(SAMPLE, "Nonexistent")
    message = str(exc.value)
    assert "Nonexistent" in message
    assert "Overview" in message
    assert "Getting Started" in message


def test_prepare_markdown_summary_to_bold():
    text = "<details>\n<summary>Relevant source files</summary>\n\n- a.md\n\n</details>"
    out = _prepare_markdown(text)
    assert "**Relevant source files**" in out
    assert "<details>" not in out
    assert "</details>" not in out
    assert "<summary>" not in out
    assert "- a.md" in out


def test_status_is_silent_when_not_a_tty(monkeypatch):
    buf = io.StringIO()  # StringIO.isatty() -> False
    monkeypatch.setattr("sys.stderr", buf)
    ran = []
    with status("Thinking..."):
        ran.append(True)
    assert ran == [True]
    assert buf.getvalue() == ""


def test_format_answer_body_only():
    assert format_answer(Answer(body="  hi  ")) == "hi"


def test_format_answer_fills_inline_citations_when_counts_match():
    a = Answer(
        body="Fiber tracks effects .",
        references=[Reference("f.py", 1, 2)],
    )
    out = format_answer(a)
    assert "effects [1]." in out
    assert "## Sources" in out
    assert "1. f.py:1-2" in out


def test_format_answer_skips_fill_when_counts_mismatch():
    a = Answer(
        body="effects . and more .",
        references=[Reference("f.py", 1, 2)],  # 2 锚点 1 引用
    )
    out = format_answer(a)
    assert "effects ." in out  # 不填充
    assert "## Sources" in out


def test_format_answer_includes_summary():
    a = Answer(body="body", summary="a summary")
    out = format_answer(a)
    assert "## Summary" in out and "a summary" in out


def test_format_answer_sources_flag_adds_slices():
    a = Answer(
        body="body .",
        references=[Reference("Repo a/b: f.py", 1, 2)],
        sources=[SourceFile("a/b", "f.py", "l1\nl2\nl3")],
    )
    out = format_answer(a, show_sources=True)
    assert "f.py:1-2" in out
    assert "l1" in out and "l2" in out

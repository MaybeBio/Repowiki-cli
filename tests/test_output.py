import io

import pytest

from repowiki.output import (
    _prepare_markdown,
    filter_page,
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

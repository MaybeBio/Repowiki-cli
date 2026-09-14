from repowiki.output import format_header, format_result


def test_format_header():
    assert format_header("facebook/react", "ask") == "## DeepWiki: facebook/react (ask)"


def test_format_result_adds_header_and_trims():
    result = format_result("facebook/react", "ask", "  some content  \n")
    assert result == "## DeepWiki: facebook/react (ask)\n\nsome content"


def test_format_result_empty_text():
    result = format_result("owner/repo", "contents", "   \n\t  ")
    assert result == "## DeepWiki: owner/repo (contents)\n\n"

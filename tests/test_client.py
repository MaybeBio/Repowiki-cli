from types import SimpleNamespace

import pytest

from repowiki.client import DeepWikiClient, ToolError


def _content(text):
    return SimpleNamespace(type="text", text=text)


def _result(is_error, texts):
    return SimpleNamespace(isError=is_error, content=[_content(t) for t in texts])


def test_extract_text_content_joins_text_parts():
    client = DeepWikiClient()
    assert client._extract_text_content(_result(False, ["line1", "line2"])) == "line1\nline2"


def test_extract_text_content_raises_on_is_error():
    client = DeepWikiClient()
    with pytest.raises(ToolError, match="boom"):
        client._extract_text_content(_result(True, ["boom"]))


def test_extract_text_content_error_without_text():
    client = DeepWikiClient()
    with pytest.raises(ToolError, match="Unknown tool error"):
        client._extract_text_content(_result(True, []))


@pytest.mark.asyncio
async def test_ask_question_builds_arguments():
    client = DeepWikiClient()
    calls = []

    async def fake_call(tool_name, arguments):
        calls.append((tool_name, arguments))
        return "answer"

    client._call_tool = fake_call
    result = await client.ask_question("facebook/react", "What is Fiber?")
    assert result == "answer"
    assert calls == [("ask_question", {"repoName": "facebook/react", "question": "What is Fiber?"})]


@pytest.mark.asyncio
async def test_read_wiki_structure_builds_arguments():
    client = DeepWikiClient()
    calls = []

    async def fake_call(tool_name, arguments):
        calls.append((tool_name, arguments))
        return "toc"

    client._call_tool = fake_call
    result = await client.read_wiki_structure("facebook/react")
    assert result == "toc"
    assert calls == [("read_wiki_structure", {"repoName": "facebook/react"})]

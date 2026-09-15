import builtins
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from repowiki import client as client_mod
from repowiki.client import (
    ConnectionError,
    DeepWikiClient,
    ToolError,
    _is_connection_failure,
    _root_cause,
)


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
    assert result.body == "answer"
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


def test_root_cause_identity_for_plain_exception():
    exc = RuntimeError("boom")
    assert _root_cause(exc) is exc


def test_root_cause_unwraps_exception_group():
    group_cls = getattr(builtins, "BaseExceptionGroup", None)
    if group_cls is None:
        pytest.skip("BaseExceptionGroup requires Python 3.11+")
    leaf = RuntimeError("boom")
    assert _root_cause(group_cls("nested", [leaf])) is leaf


def test_is_connection_failure():
    assert _is_connection_failure(OSError("Connection refused")) is True
    assert _is_connection_failure(httpx.ConnectError("boom")) is True
    assert _is_connection_failure(RuntimeError("boom")) is False


@asynccontextmanager
async def _raising_streamablehttp(url, exc):
    raise exc
    yield  # pragma: no cover


@pytest.mark.asyncio
async def test_call_tool_classifies_connection_failure(monkeypatch):
    monkeypatch.setattr(
        client_mod,
        "streamablehttp_client",
        lambda url: _raising_streamablehttp(url, ConnectionRefusedError("Connection refused")),
    )
    client = DeepWikiClient()
    with pytest.raises(ConnectionError):
        await client._call_tool("read_wiki_structure", {"repoName": "x/y"})


@pytest.mark.asyncio
async def test_call_tool_classifies_tool_failure(monkeypatch):
    monkeypatch.setattr(
        client_mod,
        "streamablehttp_client",
        lambda url: _raising_streamablehttp(url, RuntimeError("boom")),
    )
    client = DeepWikiClient()
    with pytest.raises(ToolError, match="boom"):
        await client._call_tool("read_wiki_structure", {"repoName": "x/y"})


@pytest.mark.asyncio
async def test_call_tool_surfaces_tool_error_message(monkeypatch):
    result = _result(True, ["Repository not found"])

    @asynccontextmanager
    async def fake_streamablehttp(url):
        yield (object(), object(), object())

    class _FakeSession:
        async def initialize(self):
            return None

        async def call_tool(self, tool_name, arguments):
            return result

    @asynccontextmanager
    async def fake_client_session(read, write):
        yield _FakeSession()

    monkeypatch.setattr(client_mod, "streamablehttp_client", fake_streamablehttp)
    monkeypatch.setattr(client_mod, "ClientSession", fake_client_session)

    client = DeepWikiClient()
    with pytest.raises(ToolError, match="Repository not found"):
        await client._call_tool("read_wiki_structure", {"repoName": "x/y"})


@pytest.mark.asyncio
async def test_call_tool_retries_connection_failure_once(monkeypatch):
    attempts = {"n": 0}

    @asynccontextmanager
    async def flaky_streamablehttp(url):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionRefusedError("Connection refused")
        yield (object(), object(), object())

    class _FakeSession:
        async def initialize(self):
            return None

        async def call_tool(self, tool_name, arguments):
            return _result(False, ["ok"])

    @asynccontextmanager
    async def fake_client_session(read, write):
        yield _FakeSession()

    monkeypatch.setattr(client_mod, "streamablehttp_client", flaky_streamablehttp)
    monkeypatch.setattr(client_mod, "ClientSession", fake_client_session)

    client = DeepWikiClient()
    assert await client._call_tool("read_wiki_structure", {"repoName": "x/y"}) == "ok"
    assert attempts["n"] == 2


@pytest.mark.asyncio
async def test_persistent_session_reuses_connection(monkeypatch):
    state = {"initialized": 0, "calls": 0}

    @asynccontextmanager
    async def fake_streamablehttp(url):
        yield (object(), object(), object())

    class _FakeSession:
        async def initialize(self):
            state["initialized"] += 1

        async def call_tool(self, tool_name, arguments):
            state["calls"] += 1
            return _result(False, [f"answer-{state['calls']}"])

    @asynccontextmanager
    async def fake_client_session(read, write):
        yield _FakeSession()

    monkeypatch.setattr(client_mod, "streamablehttp_client", fake_streamablehttp)
    monkeypatch.setattr(client_mod, "ClientSession", fake_client_session)

    async with DeepWikiClient() as client:
        first = await client.ask_question("facebook/react", "q1")
        second = await client.ask_question("facebook/react", "q2")

    assert state["initialized"] == 1
    assert state["calls"] == 2
    assert first.body == "answer-1"
    assert second.body == "answer-2"

import httpx
import pytest

from repowiki import devin as devin_mod
from repowiki.client import ConnectionError, ToolError
from repowiki.devin import parse_response
from repowiki.model import SourceFile


def _ev(t, data):
    return {"type": t, "data": data}


def test_parse_response_assembles_answer():
    query = {
        "state": "done",
        "error": None,
        "response": [
            _ev("chunk", "Hello "),
            _ev("chunk", "world"),
            _ev("summary_chunk", "A summary"),
            _ev("reference", {"file_path": "Repo a/b: f.py", "range_start": 1, "range_end": 5}),
            _ev("file_contents", ["a/b", "f.py", "line1\nline2\nline3"]),
            _ev("stats", {"key": "load", "value": 0.5}),
            _ev("done", None),
        ],
    }
    a = parse_response(query, "qid-1")
    assert a.body == "Hello world"
    assert a.summary == "A summary"
    assert a.query_id == "qid-1"
    assert len(a.references) == 1
    assert a.references[0].file_path == "Repo a/b: f.py"
    assert a.references[0].range_start == 1 and a.references[0].range_end == 5
    assert a.sources == [SourceFile("a/b", "f.py", "line1\nline2\nline3")]
    assert a.stats == {"load": 0.5}


def test_parse_response_dedupes_sources():
    query = {"response": [
        _ev("file_contents", ["a/b", "f.py", "x"]),
        _ev("file_contents", ["a/b", "f.py", "x"]),
        _ev("file_contents", ["a/b", "g.py", "y"]),
    ]}
    assert len(parse_response(query, None).sources) == 2


def test_parse_response_summary_none_when_empty():
    a = parse_response({"response": [_ev("chunk", "body")]}, None)
    assert a.summary is None and a.body == "body"


class _Resp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("GET", "http://x"),
                response=httpx.Response(self.status_code),
            )

    def json(self):
        return self._data


class _FakeAsyncClient:
    """Scripted httpx.AsyncClient stand-in.

    A single-item ``gets`` list repeats forever (for timeout tests);
    a multi-item list pops one per call (for normal polling).
    """

    def __init__(self, gets, post=None, post_exc=None):
        self._gets = list(gets)
        self._post = post if post is not None else {"status": "success"}
        self._post_exc = post_exc
        self.post_calls = []
        self.get_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def post(self, url, json=None):
        self.post_calls.append((url, json))
        if self._post_exc:
            raise self._post_exc
        return _Resp(self._post)

    async def get(self, url):
        self.get_calls.append(url)
        if self._post_exc:
            raise self._post_exc
        data = self._gets[0] if len(self._gets) == 1 else self._gets.pop(0)
        # Real api.devin.ai returns {"queries": [...]}; wrap to match the wire format.
        return _Resp({"queries": [data]})


@pytest.mark.asyncio
async def test_devin_ask_builds_payload_and_parses(monkeypatch):
    done = {"state": "done", "error": None, "response": [{"type": "chunk", "data": "hi"}]}
    fake = _FakeAsyncClient(gets=[done])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)

    answer = await devin_mod.DevinClient(base_url="https://example.com").ask(
        "a/b", "q?", mode="deep", poll_interval=0
    )

    assert answer.body == "hi"
    url, payload = fake.post_calls[0]
    assert url == "/ada/query"
    assert payload["engine_id"] == "agent"
    assert payload["repo_names"] == ["a/b"]
    assert payload["user_query"] == "q?"
    assert payload["attached_context"] == []
    assert payload["query_id"] == answer.query_id
    assert len(fake.get_calls) == 1


@pytest.mark.asyncio
async def test_devin_ask_connection_failure(monkeypatch):
    fake = _FakeAsyncClient(gets=[], post_exc=httpx.ConnectError("refused"))
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ConnectionError):
        await devin_mod.DevinClient().ask("a/b", "q?")


@pytest.mark.asyncio
async def test_devin_ask_query_error(monkeypatch):
    done = {"state": "done", "error": "Repository not found", "response": []}
    fake = _FakeAsyncClient(gets=[done])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ToolError, match="Repository not found"):
        await devin_mod.DevinClient().ask("a/b", "q?", poll_interval=0)


@pytest.mark.asyncio
async def test_devin_ask_timeout(monkeypatch):
    pending = {"state": "pending", "error": None, "response": []}
    fake = _FakeAsyncClient(gets=[pending])  # 单元素 → 一直 pending
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ToolError, match="timed out"):
        await devin_mod.DevinClient().ask("a/b", "q?", poll_interval=0, timeout=0.0)


@pytest.mark.asyncio
async def test_devin_ask_keeps_polling_on_nonterminal_state(monkeypatch):
    processing = {"state": "processing", "error": None, "response": []}
    done = {"state": "done", "error": None, "response": [{"type": "chunk", "data": "hi"}]}
    fake = _FakeAsyncClient(gets=[processing, done])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    answer = await devin_mod.DevinClient().ask("a/b", "q?", poll_interval=0)
    assert answer.body == "hi"
    assert len(fake.get_calls) == 2


@pytest.mark.asyncio
async def test_devin_ask_empty_queries(monkeypatch):
    class _EmptyQueriesClient:
        def __init__(self):
            self.get_calls = 0
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return None
        async def post(self, url, json=None):
            return _Resp({"status": "success"})
        async def get(self, url):
            self.get_calls += 1
            return _Resp({"queries": []})

    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: _EmptyQueriesClient())
    with pytest.raises(ToolError, match="no query results"):
        await devin_mod.DevinClient().ask("a/b", "q?", poll_interval=0)

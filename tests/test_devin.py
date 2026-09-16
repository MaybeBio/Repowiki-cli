import json

import httpx
import pytest

from repowiki import devin as devin_mod
from repowiki.client import ConnectionError, ToolError
from repowiki.devin import parse_response
from repowiki.shared.model import SourceFile


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
    assert a.body == "Hello world[1]"
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


def test_parse_response_inserts_citation_marker_at_reference_position():
    query = {"response": [
        _ev("chunk", "see "),
        _ev("reference", {"file_path": "Repo a/b: f.py", "range_start": 1, "range_end": 2}),
        _ev("chunk", " for details, and "),
        _ev("reference", {"file_path": "Repo a/b: g.py", "range_start": 3, "range_end": 4}),
        _ev("chunk", " for more."),
    ]}
    a = parse_response(query, None)
    assert a.body == "see [1] for details, and [2] for more."
    assert [r.file_path for r in a.references] == ["Repo a/b: f.py", "Repo a/b: g.py"]


def test_parse_response_parses_inline_cite_tags():
    query = {"response": [
        _ev("chunk", 'Fiber is defined <cite repo="facebook/react" path="ReactInternalTypes.js" start="87-89" end="89" /> here .'),
    ]}
    a = parse_response(query, None)
    assert a.body == "Fiber is defined [1] here ."
    assert len(a.references) == 1
    assert a.references[0].file_path == "ReactInternalTypes.js"
    assert a.references[0].range_start == 87
    assert a.references[0].range_end == 89


def test_parse_response_cite_single_line_and_ordering():
    query = {"response": [
        _ev("chunk", 'A <cite repo="r" path="a.js" start="1-2" end="2" /> and B <cite repo="r" path="b.js" start="3" end="3" />'),
    ]}
    a = parse_response(query, None)
    assert a.body == "A [1] and B [2]"
    assert [r.file_path for r in a.references] == ["a.js", "b.js"]
    assert a.references[1].range_start == 3 and a.references[1].range_end == 3


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

    async def post(self, url, json=None, params=None):
        self.post_calls.append((url, json))
        if self._post_exc:
            raise self._post_exc
        return _Resp(self._post)

    async def get(self, url, params=None):
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
        ["a/b", "c/d"], "q?", mode="deep", poll_interval=0, context="ctx", generate_summary=False
    )

    assert answer.body == "hi"
    url, payload = fake.post_calls[0]
    assert url == "/ada/query"
    assert payload["engine_id"] == "agent"
    assert payload["repo_names"] == ["a/b", "c/d"]
    assert payload["user_query"] == "q?"
    assert payload["additional_context"] == "ctx"
    assert payload["generate_summary"] is False
    assert payload["attached_context"] == []
    assert payload["query_id"] == answer.query_id
    assert len(fake.get_calls) == 1


@pytest.mark.asyncio
async def test_devin_ask_connection_failure(monkeypatch):
    fake = _FakeAsyncClient(gets=[], post_exc=httpx.ConnectError("refused"))
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ConnectionError):
        await devin_mod.DevinClient().ask(["a/b"], "q?")


@pytest.mark.asyncio
async def test_devin_ask_http_error_surfaces_detail(monkeypatch):
    exc = httpx.HTTPStatusError(
        "400",
        request=httpx.Request("POST", "http://x"),
        response=httpx.Response(400, json={"detail": "Repos not found"}),
    )
    fake = _FakeAsyncClient(gets=[], post_exc=exc)
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ToolError, match="Repos not found"):
        await devin_mod.DevinClient().ask(["a/b"], "q?")


@pytest.mark.asyncio
async def test_devin_ask_query_error(monkeypatch):
    done = {"state": "done", "error": "Repository not found", "response": []}
    fake = _FakeAsyncClient(gets=[done])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ToolError, match="Repository not found"):
        await devin_mod.DevinClient().ask(["a/b"], "q?", poll_interval=0)


@pytest.mark.asyncio
async def test_devin_ask_timeout(monkeypatch):
    pending = {"state": "pending", "error": None, "response": []}
    fake = _FakeAsyncClient(gets=[pending])  # 单元素 → 一直 pending
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ToolError, match="timed out"):
        await devin_mod.DevinClient().ask(["a/b"], "q?", poll_interval=0, timeout=0.0)


@pytest.mark.asyncio
async def test_devin_ask_timeout_skips_polling(monkeypatch):
    pending = {"state": "pending", "error": None, "response": []}
    fake = _FakeAsyncClient(gets=[pending])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ToolError, match="timed out"):
        await devin_mod.DevinClient().ask(["a/b"], "q?", poll_interval=0, timeout=0.0)
    assert fake.get_calls == []


@pytest.mark.asyncio
async def test_devin_ask_unknown_mode():
    with pytest.raises(ToolError, match="unknown mode"):
        await devin_mod.DevinClient().ask(["a/b"], "q?", mode="bogus")


@pytest.mark.asyncio
async def test_devin_ask_keeps_polling_on_nonterminal_state(monkeypatch):
    processing = {"state": "processing", "error": None, "response": []}
    done = {"state": "done", "error": None, "response": [{"type": "chunk", "data": "hi"}]}
    fake = _FakeAsyncClient(gets=[processing, done])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    answer = await devin_mod.DevinClient().ask(["a/b"], "q?", poll_interval=0)
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
        async def post(self, url, json=None, params=None):
            return _Resp({"status": "success"})
        async def get(self, url, params=None):
            self.get_calls += 1
            return _Resp({"queries": []})

    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: _EmptyQueriesClient())
    with pytest.raises(ToolError, match="no query results"):
        await devin_mod.DevinClient().ask(["a/b"], "q?", poll_interval=0)


@pytest.mark.asyncio
async def test_get_json_passes_params(monkeypatch):
    captured = {}

    class _Rec:
        status_code = 200
        def __init__(self, data):
            self._data = data
        def raise_for_status(self):
            pass
        def json(self):
            return self._data

    class _Client:
        def __init__(self, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass
        async def get(self, path, params=None):
            captured["path"] = path
            captured["params"] = params
            return _Rec({"ok": True})

    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", _Client)
    data = await devin_mod.DevinClient(base_url="https://example.com")._get_json(
        "/ada/list_public_indexes", params={"search_repo": "react"}
    )
    assert data == {"ok": True}
    assert captured["path"] == "/ada/list_public_indexes"
    assert captured["params"] == {"search_repo": "react"}


class _MgmtClient:
    def __init__(self, responses, method=None):
        self._responses = list(responses)
        self._method = method
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        return _Resp(self._responses.pop(0))

    async def post(self, path, params=None, json=None):
        self.calls.append(("POST", path, params))
        return _Resp(self._responses.pop(0))


@pytest.mark.asyncio
async def test_list_public_indexes(monkeypatch):
    fake = _MgmtClient([{"indices": [{"repo_name": "a/b"}], "needs_reindex": [], "pending_repos": []}])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    result = await devin_mod.DevinClient().list_public_indexes("react")
    assert result["indices"][0]["repo_name"] == "a/b"
    assert fake.calls == [("GET", "/ada/list_public_indexes", {"search_repo": "react"})]


@pytest.mark.asyncio
async def test_management_get_http_error_surfaces_detail(monkeypatch):
    exc = httpx.HTTPStatusError(
        "500",
        request=httpx.Request("GET", "http://x"),
        response=httpx.Response(500, json={"detail": "boom"}),
    )
    fake = _FakeAsyncClient(gets=[], post_exc=exc)
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ToolError, match="boom"):
        await devin_mod.DevinClient().list_public_indexes("react")


@pytest.mark.asyncio
async def test_public_repo_indexing_status(monkeypatch):
    fake = _MgmtClient([{"status": "completed"}])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    result = await devin_mod.DevinClient().public_repo_indexing_status("a/b")
    assert result == {"status": "completed"}
    assert fake.calls == [("GET", "/ada/public_repo_indexing_status", {"repo_name": "a/b"})]


@pytest.mark.asyncio
async def test_warm_public_repo(monkeypatch):
    fake = _MgmtClient([{"status": "OK"}])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    result = await devin_mod.DevinClient().warm_public_repo("a/b")
    assert result == {"status": "OK"}
    assert fake.calls == [("POST", "/ada/warm_public_repo", {"repo_name": "a/b"})]


@pytest.mark.asyncio
async def test_get_query_parses_answer(monkeypatch):
    q = {"state": "done", "error": None, "response": [{"type": "chunk", "data": "hi"}]}
    fake = _MgmtClient([{"queries": [q]}])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    answer = await devin_mod.DevinClient().get_query("qid-1")
    assert answer.body == "hi"
    assert answer.query_id == "qid-1"
    assert fake.calls == [("GET", "/ada/query/qid-1", None)]


@pytest.mark.asyncio
async def test_get_query_empty_queries(monkeypatch):
    fake = _MgmtClient([{"queries": []}])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ToolError, match="no query results"):
        await devin_mod.DevinClient().get_query("qid-1")


@pytest.mark.asyncio
async def test_get_query_error_field(monkeypatch):
    q = {"state": "error", "error": "boom", "response": []}
    fake = _MgmtClient([{"queries": [q]}])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ToolError, match="boom"):
        await devin_mod.DevinClient().get_query("qid-1")


@pytest.mark.asyncio
async def test_devin_ask_reuses_one_connection(monkeypatch):
    processing = {"state": "processing", "error": None, "response": []}
    done = {"state": "done", "error": None, "response": [{"type": "chunk", "data": "hi"}]}
    fake = _FakeAsyncClient(gets=[processing, done])
    created = []

    def factory(**kw):
        created.append(kw)
        return fake

    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", factory)
    answer = await devin_mod.DevinClient().ask("a/b", "q?", poll_interval=0)
    assert answer.body == "hi"
    assert len(created) == 1


class _FakeWS:
    """Scripted websockets stand-in: pops one serialized message per recv()."""

    def __init__(self, messages):
        self._messages = list(messages)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def recv(self):
        return self._messages.pop(0)


def _ws_event(kind, data=None):
    payload = {"type": kind}
    if data is not None:
        payload["data"] = data
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_devin_ask_streams_chunks_over_websocket(monkeypatch):
    messages = [
        _ws_event("chunk", "Hello "),
        _ws_event("chunk", "world"),
        _ws_event("chunk", "!"),
        _ws_event("summary_chunk", "A summary"),
        _ws_event("reference", {"file_path": "Repo a/b: f.py", "range_start": 1, "range_end": 3}),
        _ws_event("file_contents", ["a/b", "f.py", "line1\nline2\nline3"]),
        _ws_event("stats", {"key": "load", "value": 0.5}),
        _ws_event("done"),
    ]
    fake = _FakeAsyncClient(gets=[])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    monkeypatch.setattr(devin_mod.websockets, "connect", lambda url: _FakeWS(messages))

    chunks = []
    answer = await devin_mod.DevinClient().ask(["a/b"], "q?", poll_interval=0, on_chunk=chunks.append)
    assert chunks == ["Hello ", "world", "!", "[1]"]
    assert answer.body == "Hello world![1]"
    assert answer.summary == "A summary"
    assert [r.file_path for r in answer.references] == ["Repo a/b: f.py"]
    assert answer.sources == [SourceFile("a/b", "f.py", "line1\nline2\nline3")]
    assert answer.stats == {"load": 0.5}
    assert fake.get_calls == []  # no follow-up GET; the WS delivers the full answer


@pytest.mark.asyncio
async def test_devin_ask_stream_emits_citation_markers(monkeypatch):
    messages = [
        _ws_event("chunk", "see "),
        _ws_event("reference", {"file_path": "Repo a/b: f.py", "range_start": 1, "range_end": 2}),
        _ws_event("chunk", " and "),
        _ws_event("reference", {"file_path": "Repo a/b: g.py", "range_start": 3, "range_end": 4}),
        _ws_event("chunk", " more."),
        _ws_event("done"),
    ]
    fake = _FakeAsyncClient(gets=[])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    monkeypatch.setattr(devin_mod.websockets, "connect", lambda url: _FakeWS(messages))

    chunks = []
    answer = await devin_mod.DevinClient().ask(["a/b"], "q?", poll_interval=0, on_chunk=chunks.append)
    assert chunks == ["see ", "[1]", " and ", "[2]", " more."]
    assert answer.body == "see [1] and [2] more."
    assert [r.file_path for r in answer.references] == ["Repo a/b: f.py", "Repo a/b: g.py"]


@pytest.mark.asyncio
async def test_devin_ask_stream_timeout(monkeypatch):
    fake = _FakeAsyncClient(gets=[])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)
    monkeypatch.setattr(devin_mod.websockets, "connect", lambda url: _FakeWS([]))
    with pytest.raises(ToolError, match="timed out"):
        await devin_mod.DevinClient().ask(
            ["a/b"], "q?", poll_interval=0, on_chunk=lambda c: None, timeout=0.0
        )


@pytest.mark.asyncio
async def test_devin_ask_stream_connection_failure(monkeypatch):
    fake = _FakeAsyncClient(gets=[])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)

    def failing_connect(url):
        raise devin_mod.WebSocketException("refused")

    monkeypatch.setattr(devin_mod.websockets, "connect", failing_connect)
    with pytest.raises(ConnectionError, match="WebSocket"):
        await devin_mod.DevinClient().ask(["a/b"], "q?", on_chunk=lambda c: None)


@pytest.mark.asyncio
async def test_devin_ask_stream_os_error_maps_to_connection_error(monkeypatch):
    fake = _FakeAsyncClient(gets=[])
    monkeypatch.setattr(devin_mod.httpx, "AsyncClient", lambda **kw: fake)

    def refused_connect(url):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(devin_mod.websockets, "connect", refused_connect)
    with pytest.raises(ConnectionError, match="WebSocket"):
        await devin_mod.DevinClient().ask(["a/b"], "q?", on_chunk=lambda c: None)

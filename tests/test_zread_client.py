import json
import ssl

import httpx
import pytest

from repowiki.services.zread.client import (
    ZreadClient,
    ZreadChallengeError,
    ZreadConnectionError,
    ZreadError,
    ZreadNotFoundError,
    _parse_sse_body,
)
from repowiki.shared.async_ import run_async


async def _no_sleep(_delay: float) -> None:
    return None


def _wiki_json(pages=1):
    return {
        "code": 0,
        "data": {
            "info": {"wiki_id": "w1", "repo_id": "r1"},
            "pages": [
                {"page_id": f"p{i}", "slug": f"s{i}", "topic": f"T{i}", "order": i}
                for i in range(pages)
            ],
        },
    }


def test_repo_info_hits_repo_endpoint():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["locale"] = request.headers.get("x-locale")
        return httpx.Response(200, json={"code": 0, "data": {"repo_id": "r1", "wiki_id": "w1"}})

    client = ZreadClient(transport=httpx.MockTransport(handler), lang="zh")
    info = run_async(client.repo_info("o/r"))
    assert info["repo_id"] == "r1"
    assert "api/v1/repo/github/o/r" in seen["url"]
    assert seen["locale"] == "zh"


def test_retries_on_transient_status(monkeypatch):
    import repowiki.services.zread.client as mod

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(504)
        return httpx.Response(200, json={"code": 0, "data": []})

    client = ZreadClient(transport=httpx.MockTransport(handler), retries=5)
    assert run_async(client.trending()) == []
    assert calls["n"] == 3


def test_exhausted_transient_raises_connection_error(monkeypatch):
    import repowiki.services.zread.client as mod

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)

    def handler(request):
        return httpx.Response(504)

    client = ZreadClient(transport=httpx.MockTransport(handler), retries=2)
    with pytest.raises(ZreadConnectionError):
        run_async(client.trending())


def test_challenge_raises_on_403():
    def handler(request):
        return httpx.Response(403)

    client = ZreadClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ZreadChallengeError):
        run_async(client.trending())


def test_not_found_raises_on_404():
    def handler(request):
        return httpx.Response(404)

    client = ZreadClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ZreadNotFoundError):
        run_async(client.trending())


def test_envelope_error_raises():
    def handler(request):
        return httpx.Response(200, json={"code": 1, "msg": "boom"})

    client = ZreadClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ZreadError, match="boom"):
        run_async(client.trending())


def test_bad_request_surfaces_body():
    def handler(request):
        return httpx.Response(400, json={"code": 1, "msg": "repo already submitted"})

    client = ZreadClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ZreadError, match="repo already submitted"):
        run_async(client.search_repos("x"))


def test_bad_request_surfaces_raw_body():
    def handler(request):
        return httpx.Response(400, text="nope")

    client = ZreadClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ZreadError, match="nope"):
        run_async(client.search_repos("x"))


def test_submit_requires_token():
    client = ZreadClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200)), token=None
    )
    with pytest.raises(ZreadError, match="ZREAD_TOKEN"):
        run_async(client.submit("o/r"))


def test_submit_hits_endpoint_with_bearer():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"code": 0, "data": {"ok": True}})

    client = ZreadClient(transport=httpx.MockTransport(handler), token="tok")
    assert run_async(client.submit("o/r")) == {"ok": True}
    assert "api/v1/public/repo/submit" in seen["url"]
    assert seen["body"] == {"name_or_path": "o/r", "notification_email": "example@zread.ai"}
    assert seen["auth"] == "Bearer tok"


def test_search_wiki_hits_endpoint():
    seen = {}

    def handler(request):
        url = str(request.url)
        if "repo/github" in url:
            return httpx.Response(200, json={"code": 0, "data": {"repo_id": "r1", "wiki_id": "w1"}})
        seen["url"] = url
        return httpx.Response(
            200, json={"code": 0, "data": [{"title": "T", "slug": "s", "matches": []}]}
        )

    client = ZreadClient(transport=httpx.MockTransport(handler))
    results = run_async(client.search_wiki("o/r", "needle"))
    assert results[0]["title"] == "T"
    assert "api/v1/wiki/w1/search" in seen["url"]
    assert "q=needle" in seen["url"]


def test_search_wiki_requires_wiki_id():
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {}})

    client = ZreadClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ZreadNotFoundError, match="wiki_id"):
        run_async(client.search_wiki("o/r", "needle"))


def test_refresh_hits_endpoint():
    seen = {}

    def handler(request):
        url = str(request.url)
        if "repo/github" in url:
            return httpx.Response(200, json={"code": 0, "data": {"repo_id": "r1", "wiki_id": "w1"}})
        seen["url"] = url
        seen["method"] = request.method
        return httpx.Response(200, json={"code": 0, "data": {}})

    client = ZreadClient(transport=httpx.MockTransport(handler))
    data = run_async(client.refresh("o/r"))
    assert data == {"repo_id": "r1", "ok": True}
    assert "api/v1/repo/r1/refresh" in seen["url"]
    assert seen["method"] == "POST"


def test_refresh_requires_repo_id():
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {}})

    client = ZreadClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ZreadNotFoundError, match="repo_id"):
        run_async(client.refresh("o/r"))


def test_eta_hits_endpoint():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"code": 0, "data": {"backlog": 6, "estimate_minutes": 34}})

    client = ZreadClient(transport=httpx.MockTransport(handler))
    assert run_async(client.eta()) == {"backlog": 6, "estimate_minutes": 34}
    assert "api/v1/repo/eta" in seen["url"]


def test_github_head_hits_github_api():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "sha": "abc123",
                "commit": {"committer": {"date": "2026-08-19T10:00:00Z"}},
            },
        )

    client = ZreadClient(transport=httpx.MockTransport(handler))
    head = run_async(client.github_head("o/r"))
    assert head == {"sha": "abc123", "when": "2026-08-19T10:00:00Z"}
    assert "api.github.com/repos/o/r/commits/HEAD" in seen["url"]


def test_outline_hits_wiki_endpoint():
    seen = {}

    def handler(request):
        url = str(request.url)
        if "repo/github" in url:
            return httpx.Response(200, json={"code": 0, "data": {"repo_id": "r1", "wiki_id": "w1"}})
        seen["url"] = url
        return httpx.Response(200, json=_wiki_json(2))

    client = ZreadClient(transport=httpx.MockTransport(handler))
    _, pages = run_async(client.outline("o/r"))
    assert [p.slug for p in pages] == ["s0", "s1"]
    assert "api/v1/wiki/w1" in seen["url"]


def test_page_hits_wiki_page_endpoint():
    seen = {}

    def handler(request):
        url = str(request.url)
        if "repo/github" in url:
            return httpx.Response(200, json={"code": 0, "data": {"repo_id": "r1", "wiki_id": "w1"}})
        seen["url"] = url
        return httpx.Response(
            200,
            json={"code": 0, "data": {"level": "Beginner", "content": "---\nslug: s0\n---\n\n# Body"}},
        )

    client = ZreadClient(transport=httpx.MockTransport(handler))
    md = run_async(client.page("o/r", "s0"))
    assert "api/v1/wiki/w1/page/s0" in seen["url"]
    assert "# Body" in md
    assert "slug:" not in md


def test_parse_sse_body_buffers_round_finish():
    lines = [
        "event: answer",
        'data: {"text": "hel"}',
        "event: round_finish",
        'data: {"text": "hello world"}',
        "event: finish",
        "data: {}",
    ]
    assert _parse_sse_body(lines) == "hello world"


def test_parse_sse_body_joins_multiple_rounds():
    lines = [
        "event: round_finish",
        'data: {"text": "first"}',
        "event: round_finish",
        'data: {"text": "second"}',
        "event: finish",
        "data: {}",
    ]
    assert _parse_sse_body(lines) == "first\nsecond"


def test_parse_sse_body_errors_on_error_event():
    with pytest.raises(ZreadError, match="error"):
        _parse_sse_body(["event: error", "data: {}"])


def test_ask_requires_token():
    client = ZreadClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)), token=None)
    with pytest.raises(ZreadError, match="ZREAD_TOKEN"):
        run_async(client.ask("o/r", "q?"))


def test_ask_flow(monkeypatch):
    import repowiki.services.zread.client as mod

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)
    seen = {}

    sse = (
        'event: answer\ndata: {"text": "hel"}\n\n'
        'event: round_finish\ndata: {"text": "hello world"}\n\n'
        'event: finish\ndata: {}\n\n'
    )

    def handler(request):
        url = str(request.url)
        if url.endswith("/api/v1/talk"):
            return httpx.Response(200, json={"code": 0, "data": {"talk_id": "t1"}})
        if "/message" in url:
            seen["auth"] = request.headers.get("Authorization")
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})
        if "repo/github" in url:
            return httpx.Response(200, json={"code": 0, "data": {"repo_id": "r1", "wiki_id": "w1"}})
        if "/api/v1/wiki/" in url:
            return httpx.Response(200, json=_wiki_json(1))
        return httpx.Response(404)

    client = ZreadClient(transport=httpx.MockTransport(handler), token="tok", model="glm-5.1")
    answer = run_async(client.ask("o/r", "q?"))
    assert answer == "hello world"
    assert seen["auth"] == "Bearer tok"
    assert seen["body"]["model"] == "glm-5.1"
    assert seen["body"]["context"]["wiki"] == {"page_id": "p0", "wiki_id": "w1"}


def test_is_cert_error_detects_ssl_verification():
    from repowiki.services.zread.client import _is_cert_error

    cert = ssl.SSLCertVerificationError(1, "certificate verify failed")
    exc = httpx.ConnectError("certificate verify failed")
    exc.__cause__ = cert
    assert _is_cert_error(exc)
    assert not _is_cert_error(httpx.ConnectError("connection refused"))

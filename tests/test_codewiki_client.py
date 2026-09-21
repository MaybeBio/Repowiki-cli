import json
import ssl

import httpx
import pytest

from repowiki.services.codewiki.client import CodeWikiClient, extract_bootstrap
from repowiki.shared.async_ import run_async

SAMPLE_HTML = (
    "<html><script>window.WIZ_global_data = "
    '{"cfb2h":"boq_test_x","FdrFJe":"-12345","other":1};</script></html>'
)


def test_extract_bootstrap_pulls_bl_and_sid():
    bs = extract_bootstrap(SAMPLE_HTML)
    assert bs.bl == "boq_test_x"
    assert bs.sid == "-12345"


def test_extract_bootstrap_errors_when_missing():
    with pytest.raises(ValueError, match="WIZ_global_data"):
        extract_bootstrap("<html>nothing here</html>")


def test_read_wiki_builds_batchexecute_request(monkeypatch):
    seen = {}

    # Build the batchexecute response programmatically (avoids hand-escaped JSON).
    # payload = [[["o/r", "sha"], []]]  →  wiki.repo_slug == "o/r", zero sections.
    inner = json.dumps([[[ "o/r", "sha" ], []]])
    frame = ["wrb.fr", "VSX6ub", inner, None, None, None, "generic"]
    body = ")]}'\n" + json.dumps([frame])

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, text=body)

    monkeypatch.setenv("CODEWIKI_CACHE_DIR", "/tmp/codewiki-test-cache")
    client = CodeWikiClient(transport=httpx.MockTransport(handler))
    wiki = run_async(client.read_wiki("o/r"))

    assert "batchexecute" in seen["url"]
    assert "rpcids=VSX6ub" in seen["url"]
    assert "source-path=%2Fgithub.com%2Fo%2Fr" in seen["url"]
    assert seen["body"].startswith("f.req=")
    assert wiki.repo_slug == "o/r"


def test_is_cert_error_detects_ssl_verification():
    from repowiki.services.codewiki.client import _is_cert_error

    cert = ssl.SSLCertVerificationError(1, "certificate verify failed")
    exc = httpx.ConnectError("certificate verify failed")
    exc.__cause__ = cert
    assert _is_cert_error(exc)
    assert not _is_cert_error(httpx.ConnectError("connection refused"))


async def _no_sleep(_delay: float) -> None:
    return None


def test_call_retries_on_transient(monkeypatch):
    import repowiki.services.codewiki.client as mod

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)
    calls = {"n": 0}

    inner = json.dumps([[[ "o/r", "sha" ], []]])
    frame = ["wrb.fr", "VSX6ub", inner, None, None, None, "generic"]
    body = ")]}'\n" + json.dumps([frame])

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, text=SAMPLE_HTML)
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, text=body)

    monkeypatch.setenv("CODEWIKI_CACHE_DIR", "/tmp/codewiki-test-cache-retry")
    client = CodeWikiClient(transport=httpx.MockTransport(handler), retries=5)
    wiki = run_async(client.read_wiki("o/r"))
    assert wiki.repo_slug == "o/r"
    assert calls["n"] == 3


def test_call_honors_retry_after(monkeypatch):
    import repowiki.services.codewiki.client as mod

    sleeps = []

    async def capture_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(mod.asyncio, "sleep", capture_sleep)
    calls = {"n": 0}

    inner = json.dumps([[[ "o/r", "sha" ], []]])
    frame = ["wrb.fr", "VSX6ub", inner, None, None, None, "generic"]
    body = ")]}'\n" + json.dumps([frame])

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, text=SAMPLE_HTML)
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "100"})
        return httpx.Response(200, text=body)

    monkeypatch.setenv("CODEWIKI_CACHE_DIR", "/tmp/codewiki-test-cache-retry-after")
    client = CodeWikiClient(transport=httpx.MockTransport(handler), retries=5)
    wiki = run_async(client.read_wiki("o/r"))
    assert wiki.repo_slug == "o/r"
    assert calls["n"] == 2
    assert sleeps == [100.0]

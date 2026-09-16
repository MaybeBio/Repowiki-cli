import json

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

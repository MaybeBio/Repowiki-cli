from pathlib import Path

import pytest

from repowiki.services.codewiki.boq import decode_response, encode_request

FIXTURES = Path(__file__).parent / "fixtures" / "codewiki"


def test_encode_request_url_encodes_envelope():
    body = encode_request("VSX6ub", '["https://github.com/owner/repo"]')
    assert body.startswith("f.req=")
    assert body.endswith("&")
    decoded = body[len("f.req="):-1]
    assert "%5B%5B%5B" in decoded  # [[[ encoded
    assert "VSX6ub" in decoded
    assert "generic" in decoded


def test_decode_vsx6ub_fixture():
    body = (FIXTURES / "vsx6ub_response.txt").read_text(encoding="utf-8")
    payload = decode_response(body, "VSX6ub")
    assert payload[0][0][0] == "owner/example"
    sections = payload[0][1]
    assert len(sections) == 3
    assert sections[0][0] == "Example Overview"
    assert sections[0][1] == 1


def test_decode_egixfe_fixture():
    body = (FIXTURES / "egixfe_response.txt").read_text(encoding="utf-8")
    payload = decode_response(body, "EgIxfe")
    assert payload[0].startswith("Hello world")
    assert "[link](%2Fast-grep" in payload[0]


def test_decode_rejects_missing_prefix():
    with pytest.raises(ValueError, match="prefix"):
        decode_response("not a boq response", "VSX6ub")


def test_decode_returns_err_when_rpc_id_missing():
    body = ")]}'\n14\n[[\"e\",4,null]]\n"
    with pytest.raises(ValueError, match="wrb.fr"):
        decode_response(body, "VSX6ub")

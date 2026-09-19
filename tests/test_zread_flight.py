import json
from pathlib import Path

import pytest

from repowiki.services.zread.flight import (
    extract_flight,
    extract_markdown,
    parse_wiki,
    rewrite_callouts,
    strip_frontmatter,
)

FIXTURES = Path(__file__).parent / "fixtures" / "zread"


def _blob(text: str, ident: str = "0") -> str:
    return f"{ident}:T{len(text.encode('utf-8')):x},{text}"


def _flight_html(payload_obj: object) -> str:
    payload_str = json.dumps(payload_obj)
    return f'<script>self.__next_f.push([1,{json.dumps(payload_str)}])</script>'


def test_extract_flight_joins_and_unescapes():
    html = (
        '<script>self.__next_f.push([1,"hello "])</script>'
        '<script>self.__next_f.push([1,"world\\n"])</script>'
    )
    assert extract_flight(html) == "hello world\n"


def test_extract_flight_skips_undecodable_chunks():
    html = '<script>self.__next_f.push([1,"ok"])</script>'
    assert extract_flight(html) == "ok"


def test_parse_wiki_sorts_and_renumbers():
    node = {
        "wiki": {
            "info": {"wiki_id": "w1", "repo_id": "r1"},
            "pages": [
                {"page_id": "p2", "slug": "b", "topic": "B", "order": 1},
                {"page_id": "p1", "slug": "a", "topic": "A", "order": 0},
            ],
        }
    }
    info, pages = parse_wiki(json.dumps({"x": node}))
    assert info.wiki_id == "w1"
    assert info.repo_id == "r1"
    assert [p.slug for p in pages] == ["a", "b"]
    assert [p.order for p in pages] == [0, 1]
    assert pages[0].page_id == "p1"
    assert pages[0].topic == "A"


def test_parse_wiki_returns_none_without_pages():
    assert parse_wiki(json.dumps({"wiki": {"info": {"wiki_id": "w1"}, "pages": []}})) is None
    assert parse_wiki("no wiki here") is None


def test_extract_markdown_byte_slices_chinese():
    body = "---\nslug: overview\n---\n\n中文内容"
    payload = _blob(body) + "0:T0,trailing-garbage"
    md = extract_markdown(payload, "overview")
    assert md is not None
    assert md.startswith("---\nslug: overview")
    assert "中文内容" in md
    assert "trailing-garbage" not in md


def test_extract_markdown_matches_slug():
    a = _blob("---\nslug: one\n---\n\nfirst", "0")
    b = _blob("---\nslug: two\n---\n\nsecond", "1")
    md = extract_markdown(a + b, "two")
    assert md is not None
    assert "second" in md
    assert "first" not in md


def test_extract_markdown_none_when_no_frontmatter():
    assert extract_markdown(_blob("no frontmatter here")) is None


def test_rewrite_callouts_maps_kinds():
    assert "> [!TIP]" in rewrite_callouts("<CgxTip>a tip</CgxTip>")
    assert "> [!NOTE]" in rewrite_callouts("<CgxInfo>info</CgxInfo>")
    assert "> [!WARNING]" in rewrite_callouts("<CgxWarn>careful</CgxWarn>")
    assert "> [!CAUTION]" in rewrite_callouts("<CgxDanger>stop</CgxDanger>")
    assert "> [!CAUTION]" in rewrite_callouts("<CgxImportant>hi</CgxImportant>")
    assert "> [!NOTE]" in rewrite_callouts("<CgxUnknown>hmm</CgxUnknown>")


def test_rewrite_callouts_skips_code_blocks():
    md = "<CgxTip>a tip</CgxTip>\n\n```\n<CgxTip>not a tip</CgxTip>\n```\n"
    out = rewrite_callouts(md)
    assert "> [!TIP]" in out
    assert "<CgxTip>not a tip</CgxTip>" in out


def test_rewrite_callouts_drops_empty():
    assert rewrite_callouts("<CgxTip></CgxTip>") == ""


def test_strip_frontmatter():
    md = "---\nslug: x\n---\n\nbody"
    assert strip_frontmatter(md) == "body"


@pytest.mark.skipif(
    not (FIXTURES / "golang-go.html").exists(), reason="fixture not captured"
)
def test_real_fixture_extracts_wiki_and_markdown():
    html = (FIXTURES / "golang-go.html").read_text(encoding="utf-8")
    payload = extract_flight(html)
    assert payload
    parsed = parse_wiki(payload)
    assert parsed is not None
    _, pages = parsed
    assert pages
    assert extract_markdown(payload) is not None

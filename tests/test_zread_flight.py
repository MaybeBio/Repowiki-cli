from repowiki.services.zread.flight import (
    parse_wiki_data,
    rewrite_callouts,
    strip_frontmatter,
)


def test_parse_wiki_data_sorts_and_renumbers():
    data = {
        "info": {"wiki_id": "w1", "repo_id": "r1"},
        "pages": [
            {"page_id": "p2", "slug": "b", "topic": "B", "order": 1},
            {"page_id": "p1", "slug": "a", "topic": "A", "order": 0},
        ],
    }
    info, pages = parse_wiki_data(data)
    assert info.wiki_id == "w1"
    assert info.repo_id == "r1"
    assert [p.slug for p in pages] == ["a", "b"]
    assert [p.order for p in pages] == [0, 1]
    assert pages[0].page_id == "p1"
    assert pages[0].topic == "A"


def test_parse_wiki_data_keeps_section_and_group():
    data = {
        "info": {"wiki_id": "w1"},
        "pages": [
            {
                "page_id": "p1",
                "slug": "1-overview",
                "topic": "Overview",
                "section": "Get Started",
                "group": "",
                "order": 0,
            }
        ],
    }
    _, pages = parse_wiki_data(data)
    assert pages[0].section == "Get Started"
    assert pages[0].group == ""


def test_parse_wiki_data_skips_empty_slugs():
    data = {
        "info": {"wiki_id": "w1"},
        "pages": [
            {"page_id": "p1", "slug": "", "topic": "No slug"},
            {"page_id": "p2", "slug": "a", "topic": "A"},
        ],
    }
    _, pages = parse_wiki_data(data)
    assert [p.slug for p in pages] == ["a"]


def test_parse_wiki_data_empty_pages():
    info, pages = parse_wiki_data({"info": {"wiki_id": "w1"}, "pages": []})
    assert info.wiki_id == "w1"
    assert pages == []


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

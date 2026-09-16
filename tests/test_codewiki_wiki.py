from pathlib import Path

from repowiki.services.codewiki.boq import decode_response
from repowiki.services.codewiki.wiki import (
    parse,
    render_markdown,
    render_structure,
    resolve_links,
)

FIXTURES = Path(__file__).parent / "fixtures" / "codewiki"


def _payload():
    body = (FIXTURES / "vsx6ub_response.txt").read_text(encoding="utf-8")
    return decode_response(body, "VSX6ub")


def test_parse_extracts_repo_and_sections():
    wiki = parse(_payload())
    assert wiki.repo_slug == "owner/example"
    assert wiki.commit_sha == "abc123"
    assert len(wiki.sections) == 3
    assert wiki.sections[0].title == "Example Overview"
    assert wiki.sections[0].level == 1
    assert wiki.sections[1].title == "Section A"
    assert wiki.sections[1].level == 2


def test_parse_extracts_dot_diagrams():
    wiki = parse(_payload())
    assert len(wiki.sections[0].diagrams) == 1
    assert "digraph G" in wiki.sections[0].diagrams[0]
    assert wiki.sections[1].diagrams == []


def test_render_structure_indents_by_level():
    out = render_structure(parse(_payload()))
    assert "- Example Overview" in out
    assert "  - Section A" in out
    assert "    - Sub A.1" in out


def test_render_markdown_includes_headers_and_dot_blocks():
    out = render_markdown(parse(_payload()))
    assert "# owner/example" in out
    assert "# Example Overview" in out
    assert "## Section A" in out
    assert "### Sub A.1" in out
    assert "```dot" in out
    assert "digraph G" in out


def test_render_markdown_resolves_github_links():
    out = render_markdown(parse(_payload()))
    assert "https://github.com/owner/example/crates/cli/src/lib.rs" in out
    assert "Body of section A" in out


def test_resolve_links_passes_through_external_urls():
    assert resolve_links("[x](https://example.com/x)") == "[x](https://example.com/x)"
    assert resolve_links("[x](#anchor)") == "[x](#anchor)"


def test_resolve_links_resolves_encoded_repo_path():
    assert (
        resolve_links("[f](%2Fowner%2Frepo%2Ffile.rs)")
        == "[f](https://github.com/owner/repo/file.rs)"
    )

import json

from repowiki.codemap import codemap_to_mermaid


def _codemap(traces):
    return json.dumps(
        {
            "title": "t",
            "traces": traces,
            "description": "",
            "metadata": {},
            "workspaceInfo": {},
        }
    )


def _loc(id, title, path, line):
    return {
        "id": id,
        "title": title,
        "path": path,
        "lineNumber": line,
        "lineContent": "",
        "description": "",
    }


def _trace(id, title, locations):
    return {"id": id, "title": title, "description": "", "locations": locations}


def test_codemap_to_mermaid_renders_flowchart():
    text = _codemap(
        [
            _trace("1", "Trace One", [
                _loc("a", "Loc A", "/x/y/f.py", 10),
                _loc("b", "Loc B", "/x/y/g.py", 20),
            ]),
        ]
    )
    out = codemap_to_mermaid(text)
    assert out.startswith("flowchart TB")
    assert 'subgraph trace_1["1. Trace One"]' in out
    assert 'loc_a["Loc A\\nf.py:10"]' in out
    assert "loc_a --> loc_b" in out
    assert "style trace_1 fill:#e8f5e9,stroke:#4caf50,stroke-width:2px" in out


def test_codemap_to_mermaid_none_for_prose():
    assert codemap_to_mermaid("just prose, no json") is None


def test_codemap_to_mermaid_none_for_non_object_json():
    assert codemap_to_mermaid('[1, 2, 3]') is None


def test_codemap_to_mermaid_none_for_json_without_traces():
    assert codemap_to_mermaid('{"foo": 1}') is None


def test_codemap_to_mermaid_connects_traces_dashed():
    text = _codemap(
        [
            _trace("1", "First", [_loc("a", "A", "/p/f.py", 1)]),
            _trace("2", "Second", [_loc("b", "B", "/p/g.py", 2)]),
        ]
    )
    out = codemap_to_mermaid(text)
    assert "loc_a -.-> loc_b" in out
    assert "style trace_2 fill:#e3f2fd,stroke:#2196f3,stroke-width:2px" in out


def test_codemap_escapes_quote_and_shortens_path():
    text = _codemap(
        [
            _trace("1", 'Has "quotes"', [_loc("a", 'Say "hi"', "/a/b/c/deep.py", 7)]),
        ]
    )
    out = codemap_to_mermaid(text)
    assert "#quot;" in out
    assert "deep.py:7" in out

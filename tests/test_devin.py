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

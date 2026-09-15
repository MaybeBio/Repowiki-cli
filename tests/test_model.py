from repowiki.model import Answer, Reference, SourceFile


def test_answer_defaults_are_independent_instances():
    a = Answer(body="x")
    b = Answer(body="y")
    a.references.append(Reference("f.py"))
    a.stats["k"] = 1.0
    assert b.references == []
    assert b.stats == {}
    assert b.summary is None and b.query_id is None


def test_answer_explicit_fields():
    a = Answer(body="b", summary="s", query_id="q", truncated=True)
    assert (a.body, a.summary, a.query_id, a.truncated) == ("b", "s", "q", True)


def test_reference_and_source_fields():
    r = Reference("f.py", 1, 5)
    s = SourceFile("a/b", "f.py", "line1\nline2")
    assert (r.file_path, r.range_start, r.range_end) == ("f.py", 1, 5)
    assert (s.repo, s.path, s.content) == ("a/b", "f.py", "line1\nline2")

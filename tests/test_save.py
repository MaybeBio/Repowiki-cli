from datetime import datetime

import repowiki.save as save_mod


def test_default_save_path_format(monkeypatch):
    class Fixed:
        @staticmethod
        def now():
            return datetime(2026, 9, 15, 10, 30, 5)

    monkeypatch.setattr(save_mod, "datetime", Fixed)
    assert save_mod.default_save_path("facebook/react") == (
        "repowiki-facebook-react_20260915103005.md"
    )


def test_append_entry_creates_parent_dirs_and_appends(tmp_path):
    path = tmp_path / "sub" / "qa.md"
    save_mod.append_entry(str(path), "facebook/react", "Q1", "A1")
    save_mod.append_entry(str(path), "facebook/react", "Q2", "A2")

    text = path.read_text()
    assert text.count("**Q:**") == 2
    assert "# facebook/react · " in text
    assert "> **Q:** Q1" in text
    assert "A1" in text
    assert "> **Q:** Q2" in text
    assert "A2" in text
    assert text.count("---") == 2


def test_append_entry_strips_answer_whitespace(tmp_path):
    path = tmp_path / "qa.md"
    save_mod.append_entry(str(path), "facebook/react", "Q", "  padded  \n")
    text = path.read_text()
    assert "padded" in text
    assert "\n  padded  \n" not in text

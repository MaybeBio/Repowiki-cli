import pytest

from repowiki.shared.repo import normalize_repo


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("facebook/react", "facebook/react"),
        ("github.com/facebook/react", "facebook/react"),
        ("www.github.com/facebook/react", "facebook/react"),
        ("https://github.com/facebook/react", "facebook/react"),
        ("http://github.com/facebook/react", "facebook/react"),
        ("https://github.com/facebook/react/tree/main", "facebook/react"),
        ("https://github.com/facebook/react.git", "facebook/react"),
        ("  facebook/react  ", "facebook/react"),
    ],
)
def test_normalize_repo(raw, expected):
    assert normalize_repo(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "facebook", "facebook/", "/react", "github.com/facebook", "has space/react"],
)
def test_normalize_repo_invalid(raw):
    with pytest.raises(ValueError):
        normalize_repo(raw)

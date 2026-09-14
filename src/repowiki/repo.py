"""Repository name normalization and validation."""

from __future__ import annotations


def normalize_repo(raw: str) -> str:
    """Normalize a repo reference to ``owner/repo`` form.

    Accepts ``owner/repo``, ``github.com/owner/repo``, and full GitHub URLs
    (optionally with a trailing path such as ``/tree/main`` or a ``.git``
    suffix). Raises ``ValueError`` for anything that is not a well-formed
    repo reference.
    """
    value = raw.strip()
    if not value:
        raise ValueError("repository reference is empty")

    for scheme in ("https://", "http://"):
        if value.lower().startswith(scheme):
            value = value[len(scheme):]
            break

    lower = value.lower()
    if lower.startswith("www.github.com/"):
        value = value[len("www.github.com/"):]
    elif lower.startswith("github.com/"):
        value = value[len("github.com/"):]

    segments = [seg for seg in value.split("/") if seg]
    if len(segments) < 2:
        raise ValueError(
            f"invalid repository reference: '{raw}'. "
            "Expected owner/repo, github.com/owner/repo, or a GitHub URL."
        )

    owner, repo = segments[0], segments[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo:
        raise ValueError(f"invalid repository reference: '{raw}'")
    if any(" " in part or "\t" in part for part in (owner, repo)):
        raise ValueError(f"invalid repository reference: '{raw}'")

    return f"{owner}/{repo}"

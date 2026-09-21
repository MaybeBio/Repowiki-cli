"""Shared GitHub HEAD lookup and staleness formatting.

Every service's ``stat --stale`` compares its wiki/index commit sha against the
live GitHub HEAD commit, so the lookup and the human verdict live here instead
of three near-identical copies.
"""

from __future__ import annotations

import httpx


class GithubError(Exception):
    """GitHub API returned an error or an unexpected payload."""


def split_repo(repo: str) -> tuple[str, str]:
    owner, name = repo.split("/", 1)
    return owner, name


async def fetch_github_head(client: httpx.AsyncClient, owner: str, name: str) -> dict:
    """GET the HEAD commit for ``owner/name`` and return ``{"sha", "when"}``.

    ``client`` must be created with ``follow_redirects=True`` so renamed repos
    (which 301 to a numeric id) still resolve.
    """
    try:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{name}/commits/HEAD"
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise GithubError(f"GitHub API returned HTTP {exc.response.status_code}") from exc
    try:
        commit = resp.json()
    except ValueError as exc:
        raise GithubError("invalid JSON response from GitHub") from exc
    if not isinstance(commit, dict):
        raise GithubError("unexpected GitHub response")
    committer = commit.get("commit", {}).get("committer") or {}
    when = committer.get("date") if isinstance(committer, dict) else None
    return {"sha": commit.get("sha") or "", "when": when}


def format_stale(info: dict) -> str:
    """Render a staleness verdict from ``{"wiki_sha", "github_sha", "github_when"}``.

    The wiki sha may be a short prefix of the full 40-char GitHub sha, so a wiki
    is current when the GitHub sha ``startswith`` the wiki sha.
    """
    wiki_sha = info.get("wiki_sha") or ""
    github_sha = info.get("github_sha") or ""
    when = info.get("github_when") or ""
    if not github_sha:
        return "Could not fetch GitHub HEAD."
    if not wiki_sha:
        return "No commit sha in the wiki."
    if github_sha.startswith(wiki_sha):
        return f"最新 (up-to-date): {wiki_sha}"
    suffix = f" ({when})" if when else ""
    return f"过期 (stale): wiki {wiki_sha[:7]} != github {github_sha[:7]}{suffix}"

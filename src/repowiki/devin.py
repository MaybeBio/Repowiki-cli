"""Reverse-engineered api.devin.ai client."""

from __future__ import annotations

from repowiki.model import Answer, Reference, SourceFile


def parse_response(query: dict, query_id: str | None) -> Answer:
    """Assemble an Answer from a single query block's response events."""
    body: list[str] = []
    summary: list[str] = []
    references: list[Reference] = []
    sources: list[SourceFile] = []
    seen: set[tuple[str, str]] = set()
    stats: dict[str, float] = {}

    for event in query.get("response", []):
        kind = event.get("type")
        data = event.get("data")
        if kind == "chunk":
            body.append(data)
        elif kind == "summary_chunk":
            summary.append(data)
        elif kind == "reference":
            references.append(
                Reference(
                    file_path=data["file_path"],
                    range_start=data.get("range_start"),
                    range_end=data.get("range_end"),
                )
            )
        elif kind == "file_contents":
            repo, path, content = data
            key = (repo, path)
            if key not in seen:
                seen.add(key)
                sources.append(SourceFile(repo=repo, path=path, content=content))
        elif kind == "stats":
            stats[data["key"]] = data["value"]
        elif kind == "done":
            break

    return Answer(
        body="".join(body),
        summary="".join(summary) or None,
        references=references,
        sources=sources,
        stats=stats,
        query_id=query_id,
    )

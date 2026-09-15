"""Shared result types for wiki backends."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Reference:
    file_path: str
    range_start: int | None = None
    range_end: int | None = None


@dataclass
class SourceFile:
    repo: str
    path: str
    content: str


@dataclass
class Answer:
    body: str
    summary: str | None = None
    references: list[Reference] = field(default_factory=list)
    sources: list[SourceFile] = field(default_factory=list)
    stats: dict[str, float] = field(default_factory=dict)
    query_id: str | None = None
    truncated: bool = False

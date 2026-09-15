"""Codemap JSON → Mermaid flowchart rendering."""

from __future__ import annotations

import json
import re

_TRACE_COLORS = [
    ("#e8f5e9", "#4caf50"),
    ("#e3f2fd", "#2196f3"),
    ("#fff3e0", "#ff9800"),
    ("#f3e5f5", "#9c27b0"),
    ("#fff8e1", "#ffc107"),
    ("#fce4ec", "#e91e63"),
    ("#e0f2f1", "#009688"),
    ("#fbe9e7", "#ff5722"),
]


def _sanitize_id(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", str(value))


def _escape_label(value: str) -> str:
    return value.replace('"', "#quot;").replace("\n", " ")


def _short_path(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def codemap_to_mermaid(text: str) -> str | None:
    """Return a Mermaid flowchart for a codemap JSON blob, else None."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("traces"), list):
        return None
    return _render(data["traces"])


def _render(traces: list[dict]) -> str:
    lines = ["flowchart TB"]
    for i, trace in enumerate(traces):
        sg_id = _sanitize_id(f"trace_{trace.get('id', i)}")
        title = _escape_label(str(trace.get("title", "")))
        lines.append("")
        lines.append(f'    subgraph {sg_id}["{trace.get("id", i)}. {title}"]')
        locations = trace.get("locations", [])
        for loc in locations:
            loc_id = _sanitize_id(f"loc_{loc.get('id')}")
            loc_title = _escape_label(str(loc.get("title", "")))
            filename = _short_path(str(loc.get("path", "")))
            label = f"{loc_title}\\n{filename}:{loc.get('lineNumber', '')}"
            lines.append(f'        {loc_id}["{label}"]')
        lines.append("    end")
        for j in range(len(locations) - 1):
            a = _sanitize_id(f"loc_{locations[j].get('id')}")
            b = _sanitize_id(f"loc_{locations[j + 1].get('id')}")
            lines.append(f"    {a} --> {b}")
    for i in range(len(traces) - 1):
        curr = traces[i].get("locations", [])
        nxt = traces[i + 1].get("locations", [])
        if curr and nxt:
            a = _sanitize_id(f"loc_{curr[-1].get('id')}")
            b = _sanitize_id(f"loc_{nxt[0].get('id')}")
            lines.append(f"    {a} -.-> {b}")
    lines.append("")
    for i, trace in enumerate(traces):
        sg_id = _sanitize_id(f"trace_{trace.get('id', i)}")
        fill, stroke = _TRACE_COLORS[i % len(_TRACE_COLORS)]
        lines.append(f"    style {sg_id} fill:{fill},stroke:{stroke},stroke-width:2px")
    return "\n".join(lines)

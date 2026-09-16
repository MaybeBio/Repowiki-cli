"""Boq batchexecute request/response framing for CodeWiki."""

from __future__ import annotations

import json
from urllib.parse import quote

_PREFIX = ")]}'"


def encode_request(rpc_id: str, inner_json: str) -> str:
    """Return the ``f.req=...&`` form body for a batchexecute call."""
    envelope = [[[rpc_id, inner_json, None, "generic"]]]
    serialized = json.dumps(envelope)
    return f"f.req={quote(serialized, safe='')}&"


def decode_response(body: str, rpc_id: str) -> object:
    """Strip the ``)]}'`` prefix, skip length headers, and return the inner
    payload of the ``wrb.fr`` frame whose id matches ``rpc_id``."""
    trimmed = body.lstrip("﻿")
    if not trimmed.startswith(_PREFIX):
        raise ValueError("response missing `)]}'` prefix")
    cursor = trimmed[len(_PREFIX):]

    decoder = json.JSONDecoder()
    while True:
        start = next((i for i, ch in enumerate(cursor) if ch in "[{"), None)
        if start is None:
            break
        cursor = cursor[start:]
        frame, consumed = decoder.raw_decode(cursor)
        cursor = cursor[consumed:]
        payload = _find_rpc_payload(frame, rpc_id)
        if payload is not None:
            return payload

    raise ValueError(f"no `wrb.fr` frame found for rpc id `{rpc_id}`")


def _find_rpc_payload(frames: object, rpc_id: str) -> object | None:
    if not isinstance(frames, list):
        raise ValueError("frame is not an array")
    for frame in frames:
        if not isinstance(frame, list):
            continue
        tag = frame[0] if frame and isinstance(frame[0], str) else ""
        if tag != "wrb.fr":
            continue
        fid = frame[1] if len(frame) > 1 and isinstance(frame[1], str) else ""
        if fid != rpc_id:
            continue
        inner = frame[2] if len(frame) > 2 and isinstance(frame[2], str) else None
        if inner is None:
            raise ValueError("`wrb.fr` frame missing inner JSON string")
        return json.loads(inner)
    return None

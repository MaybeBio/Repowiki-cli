"""Shared HTTP retry/backoff primitives.

Used by services that talk to flaky upstreams (zread.ai, codewiki.google) to
retry transient failures with exponential backoff.
"""

from __future__ import annotations

import random

# Status codes worth retrying. ``429`` is also retried separately (honouring
# ``Retry-After``); Cloudflare-style edge statuses are included.
TRANSIENT_STATUS = frozenset({
    408, 425, 429, 500, 502, 503, 504,
    520, 521, 522, 523, 524, 525, 526, 527, 528, 529,
})


def backoff(attempt: int) -> float:
    """Exponential backoff with jitter, capped at 30 seconds."""
    return min(2 ** attempt + random.uniform(0.0, 1.5), 30.0)

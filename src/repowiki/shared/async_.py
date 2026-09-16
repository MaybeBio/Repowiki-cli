"""Synchronous bridge for async client calls.

Named ``async_`` (not ``async``) because ``async`` is a Python keyword and a
module by that name cannot be reached with a normal ``import`` statement.
"""

from __future__ import annotations

import asyncio
from typing import Any


def run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)

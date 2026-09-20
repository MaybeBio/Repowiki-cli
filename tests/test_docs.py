"""Guard against silently-un-namespaced CLI invocations in the docs."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_COMMANDS = (
    "structure", "contents", "ask", "list", "status", "warm", "get",
    "find", "stat", "top", "rand", "cp", "submit", "search", "refresh",
)
_BARE_INVOCATION = re.compile(r"repowiki-cli\s+(?:" + "|".join(_COMMANDS) + r")\b")


def test_readmes_use_namespaced_commands():
    for name in ("README.md", "README.zh-CN.md"):
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        matches = _BARE_INVOCATION.findall(text)
        assert not matches, (
            f"{name} has un-namespaced invocations: {matches!r}. "
            "Use `repowiki-cli deepwiki <command>`."
        )

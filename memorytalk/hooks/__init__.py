"""memory.talk hook installer — injects ``memory.talk recall --hook`` into
host AI CLIs (Claude Code, Codex, …) via their plugin systems.

Public surface:
- ``ADAPTERS``: registry of host adapters
- ``install_step()``: the wizard step entry, used by ``cli/setup.py``
"""
from __future__ import annotations

from memorytalk.hooks.base import HostAdapter, HostPresence, HostState
from memorytalk.hooks.claude_code import ClaudeCodeAdapter
from memorytalk.hooks.codex import CodexAdapter


ADAPTERS: list[HostAdapter] = [
    ClaudeCodeAdapter(),
    CodexAdapter(),
]


__all__ = [
    "ADAPTERS",
    "HostAdapter",
    "HostPresence",
    "HostState",
]

"""Adapter registry."""

from __future__ import annotations

from memory_talk.adapters.base import Adapter
from memory_talk.adapters.claude_code import ClaudeCodeAdapter


ADAPTERS: dict[str, type[Adapter]] = {
    "claude-code": ClaudeCodeAdapter,
}


def get_adapter(name: str) -> Adapter:
    cls = ADAPTERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown adapter: {name}. Available: {list(ADAPTERS.keys())}")
    return cls()

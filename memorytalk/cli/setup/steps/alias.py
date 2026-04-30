"""Wizard step: install the ``memory.talk → memory-talk`` symlink.

The link goes next to whichever ``memory-talk`` script we're running from
— that's either the dedicated venv at ``~/.memory-talk/.venv/bin`` or
the user's own env if they opted out at the bootstrap prompt. The caller
resolves that path (via ``current_memory_talk_bin()``) and passes it in.

Idempotent (see ``helpers.create_symlink``); skips cleanly if the target
is missing or the link path already points elsewhere.
"""
from __future__ import annotations
from pathlib import Path

from ..helpers import create_symlink


def _step_alias(memory_talk_bin: Path) -> dict:
    if not memory_talk_bin.exists():
        return {
            "status": "skipped_not_found",
            "message": f"{memory_talk_bin} does not exist — memory-talk not installed in this env",
        }
    link_path = memory_talk_bin.parent / "memory.talk"
    res = create_symlink(memory_talk_bin, link_path)
    return {
        "status": res.status,
        "link_path": str(res.link_path),
        "target": str(res.target),
        "message": res.message,
    }

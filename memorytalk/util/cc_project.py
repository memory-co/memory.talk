"""Claude Code project_id derivation from cwd.

Claude Code stores session JSONL files at::

    ~/.claude/projects/<project_id>/<session_uuid>.jsonl

where ``project_id`` is the absolute cwd path with ``/`` and ``.``
characters each replaced by ``-``. Verified empirically against
``~/.claude/projects/`` contents (2026-05). For example::

    /home/twwyzh                                  → -home-twwyzh
    /home/twwyzh/agent-service                    → -home-twwyzh-agent-service
    /home/twwyzh/mem-go/memory.talk/memorytalk    → -home-twwyzh-mem-go-memory-talk-memorytalk

Note that the conversion is **not invertible** — `memory-talk/` and
`memory.talk/` collide. We only ever go forward (cwd → project_id),
which is fine for our use case.
"""
from __future__ import annotations
from pathlib import Path


CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def cwd_to_project_id(cwd: Path | str) -> str:
    """Return the Claude Code project_id directory name for the given cwd.

    The cwd is resolved to an absolute path first. Both ``/`` and ``.``
    are replaced with ``-`` to mirror Claude Code's own derivation.
    """
    abs_path = str(Path(cwd).expanduser().resolve())
    return abs_path.replace("/", "-").replace(".", "-")


def claude_project_dir(cwd: Path | str) -> Path:
    """Return the Claude Code session storage directory for the given cwd."""
    return CLAUDE_PROJECTS_ROOT / cwd_to_project_id(cwd)


def is_same_path(a: Path | str, b: Path | str) -> bool:
    """Compare two paths after expanding ``~`` and resolving symlinks.

    Used by recall --hook to decide whether the calling cwd matches
    the configured explore.cwd.
    """
    return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()

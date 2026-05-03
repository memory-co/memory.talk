"""Shared fixture for explore tests.

Redirects ``Path.home()`` to a tmp dir so:
  - ``~/.claude/projects/`` lookups land in tmp space
  - the default ``explore.cwd`` (``~/.memory-talk/explore``) resolves
    to a tmp dir we can write fixture jsonls into

Returns the runner / config / explore_cwd / project_dir bundle so each
test only has to write fixture data and invoke the CLI.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from memorytalk.cli import main
from memorytalk.config import Config
from memorytalk.util.cc_project import claude_project_dir


@pytest.fixture
def explore_env(tmp_path: Path, monkeypatch):
    # Both Path.home() and the underlying os.path.expanduser look at $HOME;
    # patch both for completeness.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    data_root = tmp_path / ".memory-talk"
    data_root.mkdir()
    (data_root / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
    }))
    cfg = Config(data_root)

    explore_cwd = tmp_path / ".memory-talk" / "explore"
    explore_cwd.mkdir(parents=True)
    project_dir = claude_project_dir(explore_cwd)
    project_dir.mkdir(parents=True)

    class Env:
        pass

    env = Env()
    env.runner = CliRunner()
    env.main = main
    env.config = cfg
    env.data_root = data_root
    env.explore_cwd = explore_cwd
    env.project_dir = project_dir
    yield env


def write_jsonl(path: Path, rounds: list[dict]) -> None:
    """Write a list of round dicts as a Claude Code-shaped jsonl file."""
    path.write_text("\n".join(json.dumps(r) for r in rounds) + "\n")


def make_round(timestamp: str, *, role: str = "user", text: str | None = None,
               tool_use_command: str | None = None) -> dict:
    """Build a minimal Claude Code message dict.

    ``tool_use_command``: when set, the message contains a Bash tool_use
    block with this command — used by the card-creation heuristic.
    """
    content: list[dict]
    if tool_use_command is not None:
        content = [{
            "type": "tool_use",
            "id": "toolu_x",
            "name": "Bash",
            "input": {"command": tool_use_command},
        }]
    else:
        content = [{"type": "text", "text": text or "hi"}]
    return {
        "type": "message",
        "timestamp": timestamp,
        "message": {"role": role, "content": content},
    }

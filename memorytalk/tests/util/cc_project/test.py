"""cwd → Claude Code project_id derivation."""
from __future__ import annotations
from pathlib import Path

from memorytalk.util.cc_project import (
    CLAUDE_PROJECTS_ROOT, claude_project_dir, cwd_to_project_id, is_same_path,
)


def test_simple_cwd():
    assert cwd_to_project_id("/home/twwyzh") == "-home-twwyzh"


def test_nested_cwd():
    assert (
        cwd_to_project_id("/home/twwyzh/agent-service")
        == "-home-twwyzh-agent-service"
    )


def test_dot_in_path_segment_replaced_with_dash():
    # Empirical: /home/twwyzh/mem-go/memory.talk/memorytalk/cli/setup
    # → -home-twwyzh-mem-go-memory-talk-memorytalk-cli-setup
    assert (
        cwd_to_project_id("/home/twwyzh/mem-go/memory.talk/memorytalk/cli/setup")
        == "-home-twwyzh-mem-go-memory-talk-memorytalk-cli-setup"
    )


def test_hidden_dir_double_dash(tmp_path: Path):
    # ~/.memory-talk/explore — the leading dot in `.memory-talk` produces
    # a `--` after the parent dir. Use tmp_path to avoid resolving
    # against a real (possibly nonexistent) `.memory-talk`.
    cwd = tmp_path / ".explore"
    cwd.mkdir()
    pid = cwd_to_project_id(cwd)
    assert pid.endswith("--explore")


def test_claude_project_dir_under_claude_root(tmp_path: Path):
    cwd = tmp_path / "myproj"
    cwd.mkdir()
    d = claude_project_dir(cwd)
    assert d.parent == CLAUDE_PROJECTS_ROOT
    assert d.name == cwd_to_project_id(cwd)


def test_is_same_path_handles_tilde_and_resolution(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".memory-talk" / "explore").mkdir(parents=True)
    assert is_same_path("~/.memory-talk/explore", tmp_path / ".memory-talk" / "explore")


def test_is_same_path_distinguishes_different_dirs(tmp_path: Path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    assert not is_same_path(a, b)

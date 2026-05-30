"""hook_state.json is a cache, not a source of truth — but must
persist and recover cleanly across runs."""
from __future__ import annotations

from pathlib import Path

from memorytalk.hooks import state


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    assert state.load(tmp_path) == {}


def test_record_then_load(tmp_path: Path) -> None:
    state.record_verified(tmp_path, "claude-code", "sha256:abc")
    data = state.load(tmp_path)
    assert "claude-code" in data
    assert data["claude-code"]["plugin_dir_hash"] == "sha256:abc"
    assert "last_verified_at" in data["claude-code"]


def test_clear_removes_only_named_host(tmp_path: Path) -> None:
    state.record_verified(tmp_path, "claude-code", "h1")
    state.record_verified(tmp_path, "codex", "h2")
    state.clear(tmp_path, "claude-code")
    data = state.load(tmp_path)
    assert "claude-code" not in data
    assert "codex" in data


def test_last_verified_returns_none_when_unknown(tmp_path: Path) -> None:
    assert state.last_verified(tmp_path, "anything") is None


def test_corrupt_file_falls_back_to_empty(tmp_path: Path) -> None:
    (tmp_path / "hook_state.json").write_text("not json")
    assert state.load(tmp_path) == {}

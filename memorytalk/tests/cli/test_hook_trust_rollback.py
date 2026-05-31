"""Trust-step rollback contract: when the Codex trust loop is aborted
(or fails for any reason), the plugin install must be undone — host
plugin removed, materialized assets cleared, hook state cache cleared.
We never leave Codex in "plugin registered but never trusted" state.

This is the structural fix for the 0.8.8 dirty-state bug the user
flagged: trust failure used to return a summary dict and walk away,
leaving plugin entries lingering in ``~/.codex/config.toml``.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memorytalk.cli import setup as setup_mod
from memorytalk.hooks.base import HostPresence, HostState


@pytest.fixture
def fake_codex_adapter():
    adapter = MagicMock()
    adapter.name = "codex"
    adapter.display_name = "Codex"
    adapter.needs_trust = True
    adapter.asset_subdir = "codex"
    adapter.detect.return_value = HostPresence(
        binary_path=Path("/fake/codex"), version="0.133.0",
    )
    adapter.current_state.return_value = HostState.ABSENT
    adapter.trust_ok.return_value = False  # never trusted
    return adapter


def test_trust_abort_triggers_full_rollback(
    tmp_path, monkeypatch, fake_codex_adapter,
):
    """User Ctrl-C in trust loop → _wait_for_trust returns False →
    _apply_install must call uninstall + clear materialized + clear
    hook state, and return action=aborted-trust-rolled-back."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))

    # Pretend the user aborted the trust loop right away.
    monkeypatch.setattr(setup_mod, "_wait_for_trust", lambda a: False)

    from memorytalk.config import Config
    cfg = Config()

    materialized = tmp_path / "hook_plugins" / "codex"
    materialized.mkdir(parents=True)
    (materialized / "marker.txt").write_text("present")  # observable artifact

    # Seed hook_state to confirm rollback clears it.
    from memorytalk.hooks import state as hook_state
    hook_state.record_verified(cfg.data_root, "codex", "sha256:before")

    row = setup_mod.HookRow(
        adapter=fake_codex_adapter,
        presence=fake_codex_adapter.detect.return_value,
        state=HostState.ABSENT,
        materialized=materialized,
    )

    result = setup_mod._apply_install(row, cfg)

    # 1. Result reports the rollback, not "trust-required"
    assert result == {"host": "codex", "action": "aborted-trust-rolled-back"}, result

    # 2. Adapter.uninstall() was called
    fake_codex_adapter.uninstall.assert_called_once()

    # 3. Materialized dir removed
    assert not materialized.exists(), "materialized dir survived rollback"

    # 4. Hook state cache cleared
    assert hook_state.last_verified(cfg.data_root, "codex") is None, (
        "hook_state entry survived rollback"
    )


def test_rollback_swallows_uninstall_errors(
    tmp_path, monkeypatch, fake_codex_adapter,
):
    """If uninstall itself raises during rollback, we must still clear
    the local state and not propagate — rollback runs on an already-
    failing path, blowing up further helps nobody."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(setup_mod, "_wait_for_trust", lambda a: False)

    fake_codex_adapter.uninstall.side_effect = RuntimeError("codex CLI flaked")

    from memorytalk.config import Config
    cfg = Config()
    materialized = tmp_path / "hook_plugins" / "codex"
    materialized.mkdir(parents=True)

    row = setup_mod.HookRow(
        adapter=fake_codex_adapter,
        presence=fake_codex_adapter.detect.return_value,
        state=HostState.ABSENT,
        materialized=materialized,
    )

    # Must not raise, must still clean up local state.
    result = setup_mod._apply_install(row, cfg)
    assert result["action"] == "aborted-trust-rolled-back"
    assert not materialized.exists(), (
        "materialized must be cleared even when uninstall raises"
    )


def test_trust_granted_in_loop_completes_install(
    tmp_path, monkeypatch, fake_codex_adapter,
):
    """Opposite branch: trust eventually granted → install completes
    normally → no rollback, action=verified."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))

    monkeypatch.setattr(setup_mod, "_wait_for_trust", lambda a: True)
    monkeypatch.setattr(setup_mod, "_verify", lambda r, cfg: True)

    from memorytalk.config import Config
    cfg = Config()
    materialized = tmp_path / "hook_plugins" / "codex"
    materialized.mkdir(parents=True)

    row = setup_mod.HookRow(
        adapter=fake_codex_adapter,
        presence=fake_codex_adapter.detect.return_value,
        state=HostState.ABSENT,
        materialized=materialized,
    )

    result = setup_mod._apply_install(row, cfg)
    assert result == {"host": "codex", "action": "verified"}, result
    fake_codex_adapter.uninstall.assert_not_called()
    assert materialized.exists(), "materialized must NOT be cleared on success"

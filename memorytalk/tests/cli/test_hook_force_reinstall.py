"""When wheel-bundled hook assets change AND a plugin is already
installed in the host CLI's cache, ``_apply_install`` must
``uninstall + install`` to push the new content into that cache.

Why: Host CLIs (Codex / Claude Code) copy the plugin into their own
plugin cache at ``plugin add`` time. Once copied, they don't re-read
our marketplace directory. ``marketplace upgrade`` only re-pulls when
the plugin manifest's ``version`` field bumps. We don't bump version
on every release, so this test pins the only mechanism we have left:
forced reinstall on content change.

This is the structural fix for the 0.9.0 → 0.9.1 user-reported bug
where Codex kept calling ``recall --hook`` (the old command) even
after re-running ``memory.talk setup`` because the host cache stayed
on the pre-upgrade snapshot.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memorytalk.cli import setup as setup_mod
from memorytalk.hooks.base import HostPresence, HostState


def _adapter(name: str = "claude-code", needs_trust: bool = False):
    adapter = MagicMock()
    adapter.name = name
    adapter.display_name = name
    adapter.needs_trust = needs_trust
    adapter.asset_subdir = "claude_code"
    adapter.detect.return_value = HostPresence(
        binary_path=Path(f"/fake/{name}"), version="x.y.z",
    )
    adapter.trust_ok.return_value = True
    return adapter


def test_force_reinstall_when_assets_changed_and_already_installed(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(setup_mod, "_verify", lambda r, cfg: True)
    # materialize.materialize returns True (content changed)
    monkeypatch.setattr(
        setup_mod.hook_materialize, "materialize",
        lambda subdir, mdir: True,
    )

    adapter = _adapter()
    materialized = tmp_path / "hook_plugins" / "claude_code"
    materialized.mkdir(parents=True)

    row = setup_mod.HookRow(
        adapter=adapter,
        presence=adapter.detect.return_value,
        state=HostState.INSTALLED,         # already installed
        materialized=materialized,
    )

    from memorytalk.config import Config
    result = setup_mod._apply_install(row, Config())

    # Both uninstall AND install must have been called (in that order)
    # to push the new content into the host's plugin cache.
    method_calls = [c[0] for c in adapter.method_calls]
    assert "uninstall" in method_calls
    assert "install" in method_calls
    assert method_calls.index("uninstall") < method_calls.index("install")
    assert result["action"] == "verified"


def test_no_reinstall_when_assets_unchanged(tmp_path, monkeypatch):
    """When materialize returns False (hash matched), we MUST NOT do a
    pointless uninstall+install on every setup run."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(setup_mod, "_verify", lambda r, cfg: True)
    monkeypatch.setattr(
        setup_mod.hook_materialize, "materialize",
        lambda subdir, mdir: False,        # no change
    )

    adapter = _adapter()
    materialized = tmp_path / "hook_plugins" / "claude_code"
    materialized.mkdir(parents=True)

    row = setup_mod.HookRow(
        adapter=adapter,
        presence=adapter.detect.return_value,
        state=HostState.INSTALLED,
        materialized=materialized,
    )

    from memorytalk.config import Config
    setup_mod._apply_install(row, Config())

    method_calls = [c[0] for c in adapter.method_calls]
    assert "uninstall" not in method_calls, (
        "no content change → must NOT trigger force reinstall"
    )
    # ``install`` is still called (host-side `install()` is idempotent
    # for the absent-but-marketplace-known and similar cases; even when
    # the plugin is already installed, current code calls install which
    # does the right marketplace-update-no-op for a no-content-change run).
    assert "install" in method_calls


def test_no_reinstall_when_absent_even_if_changed(tmp_path, monkeypatch):
    """ABSENT means the plugin isn't in the host's cache at all — no
    point in calling uninstall first. Skip straight to install."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(setup_mod, "_verify", lambda r, cfg: True)
    monkeypatch.setattr(
        setup_mod.hook_materialize, "materialize",
        lambda subdir, mdir: True,
    )

    adapter = _adapter()
    materialized = tmp_path / "hook_plugins" / "claude_code"
    materialized.mkdir(parents=True)

    row = setup_mod.HookRow(
        adapter=adapter,
        presence=adapter.detect.return_value,
        state=HostState.ABSENT,            # not installed yet
        materialized=materialized,
    )

    from memorytalk.config import Config
    setup_mod._apply_install(row, Config())

    method_calls = [c[0] for c in adapter.method_calls]
    assert "uninstall" not in method_calls, (
        "fresh install path must NOT call uninstall first"
    )
    assert "install" in method_calls

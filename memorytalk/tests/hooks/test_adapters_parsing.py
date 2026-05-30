"""Adapter state detection: parse output of ``host plugin list`` and
``host plugin marketplace list`` without spawning the real CLIs.

These tests pin down the regex shapes we rely on, so format drift in
upstream CLIs surfaces as a failing test instead of silent breakage."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from memorytalk.hooks import claude_code as cc_mod
from memorytalk.hooks import codex as codex_mod
from memorytalk.hooks.base import HostState


# ───────────────────────────── Claude Code ─────────────────────────────

CC_PLUGIN_LIST_ENABLED = textwrap.dedent("""\
    Installed plugins:

      ❯ memory-talk-recall@memory-talk
        Version: 1
        Scope: user
        Status: ✔ enabled

      ❯ superpowers@claude-plugins-official
        Version: 5.1.0
        Scope: user
        Status: ✔ enabled
""")

CC_PLUGIN_LIST_DISABLED = CC_PLUGIN_LIST_ENABLED.replace("✔ enabled", "✘ disabled", 1)
CC_PLUGIN_LIST_FAILED = CC_PLUGIN_LIST_ENABLED.replace(
    "✔ enabled", "✘ failed to load", 1
)
CC_PLUGIN_LIST_ABSENT = textwrap.dedent("""\
    Installed plugins:

      ❯ superpowers@claude-plugins-official
        Version: 5.1.0
        Scope: user
        Status: ✔ enabled
""")


@pytest.fixture
def cc_adapter(tmp_path: Path, monkeypatch):
    adapter = cc_mod.ClaudeCodeAdapter()
    return adapter


def _patch_capture(monkeypatch, mod, outputs: dict[tuple, str]) -> None:
    """Stub ``_capture`` / ``_run`` so adapters don't spawn real CLIs.
    outputs: maps ``tuple(argv)`` -> stdout."""
    def _fake_capture(argv):
        return outputs.get(tuple(argv), "")
    monkeypatch.setattr(mod, "_capture", _fake_capture)


def test_cc_state_absent_when_plugin_missing(tmp_path, monkeypatch, cc_adapter):
    _patch_capture(monkeypatch, cc_mod, {
        ("claude", "plugin", "list"): CC_PLUGIN_LIST_ABSENT,
    })
    assert cc_adapter.current_state(tmp_path / "nope") == HostState.ABSENT


def test_cc_state_disabled(tmp_path, monkeypatch, cc_adapter):
    _patch_capture(monkeypatch, cc_mod, {
        ("claude", "plugin", "list"): CC_PLUGIN_LIST_DISABLED,
    })
    # We need a real materialized dir matching bundled hash to test the
    # non-drift path, but disabled short-circuits before the drift check.
    assert cc_adapter.current_state(tmp_path) == HostState.INSTALLED_DISABLED


def test_cc_state_failed(tmp_path, monkeypatch, cc_adapter):
    _patch_capture(monkeypatch, cc_mod, {
        ("claude", "plugin", "list"): CC_PLUGIN_LIST_FAILED,
    })
    assert cc_adapter.current_state(tmp_path) == HostState.INSTALLED_FAILED


def test_cc_state_drift_when_disk_hash_differs(tmp_path, monkeypatch, cc_adapter):
    _patch_capture(monkeypatch, cc_mod, {
        ("claude", "plugin", "list"): CC_PLUGIN_LIST_ENABLED,
    })
    # tmp_path is empty -> dir_hash == "" ≠ bundled hash -> DRIFT
    assert cc_adapter.current_state(tmp_path) == HostState.INSTALLED_DRIFT


# ───────────────────────────── Codex ───────────────────────────────────

CODEX_PLUGIN_LIST_INSTALLED = textwrap.dedent("""\
    Marketplace `memory-talk`
    /home/me/.memory.talk/hook_plugins/codex/.agents/plugins/marketplace.json

    PLUGIN                                STATUS         VERSION  PATH
    memory-talk-recall@memory-talk        installed      1        /home/me/...
    linear@openai-curated                 not installed
""")

CODEX_PLUGIN_LIST_ABSENT = textwrap.dedent("""\
    Marketplace `openai-curated`
    /home/me/.codex/.tmp/plugins/.agents/plugins/marketplace.json

    PLUGIN                                STATUS         VERSION  PATH
    linear@openai-curated                 not installed
""")


@pytest.fixture
def codex_adapter():
    return codex_mod.CodexAdapter()


def test_codex_state_absent(tmp_path, monkeypatch, codex_adapter):
    _patch_capture(monkeypatch, codex_mod, {
        ("codex", "plugin", "list"): CODEX_PLUGIN_LIST_ABSENT,
    })
    assert codex_adapter.current_state(tmp_path) == HostState.ABSENT


def test_codex_state_drift_when_disk_hash_differs(tmp_path, monkeypatch, codex_adapter):
    _patch_capture(monkeypatch, codex_mod, {
        ("codex", "plugin", "list"): CODEX_PLUGIN_LIST_INSTALLED,
    })
    # tmp_path empty -> drift
    assert codex_adapter.current_state(tmp_path) == HostState.INSTALLED_DRIFT


def test_codex_state_untrusted_when_no_trust_hash(
    tmp_path, monkeypatch, codex_adapter,
):
    """Installed + non-drift + no trusted_hash in config.toml -> UNTRUSTED."""
    from memorytalk.hooks import materialize
    # Materialize so on-disk hash matches bundled hash
    materialize.materialize("codex", tmp_path)

    _patch_capture(monkeypatch, codex_mod, {
        ("codex", "plugin", "list"): CODEX_PLUGIN_LIST_INSTALLED,
    })
    # Point CONFIG_PATH at a fresh empty config -> trust_ok=False
    fake_config = tmp_path / "config.toml"
    fake_config.write_text("# empty\n")
    monkeypatch.setattr(codex_mod, "CONFIG_PATH", fake_config)
    assert codex_adapter.current_state(tmp_path) == HostState.INSTALLED_UNTRUSTED


def test_codex_state_installed_when_trust_hash_present(
    tmp_path, monkeypatch, codex_adapter,
):
    from memorytalk.hooks import materialize
    materialize.materialize("codex", tmp_path)

    _patch_capture(monkeypatch, codex_mod, {
        ("codex", "plugin", "list"): CODEX_PLUGIN_LIST_INSTALLED,
    })
    fake_config = tmp_path / "config.toml"
    fake_config.write_text(textwrap.dedent(f"""\
        [hooks.state."{codex_mod.TRUST_KEY}"]
        trusted_hash = "sha256:deadbeef00000000000000000000000000000000000000000000000000000000"
    """))
    monkeypatch.setattr(codex_mod, "CONFIG_PATH", fake_config)
    assert codex_adapter.current_state(tmp_path) == HostState.INSTALLED


def test_codex_trust_ok_false_when_other_keys_present(
    tmp_path, monkeypatch, codex_adapter,
):
    """We must match the EXACT trust key — not just any trusted_hash."""
    fake_config = tmp_path / "config.toml"
    fake_config.write_text(textwrap.dedent("""\
        [hooks.state."some-other-plugin@some-other-marketplace:hooks/hooks.json:user_prompt_submit:0:0"]
        trusted_hash = "sha256:deadbeef00000000000000000000000000000000000000000000000000000000"
    """))
    monkeypatch.setattr(codex_mod, "CONFIG_PATH", fake_config)
    assert codex_adapter.trust_ok() is False

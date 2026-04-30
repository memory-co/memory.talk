"""Opt-out path: user answers 'n' to the bootstrap prompt.

The wizard must run in the *current* python env without ever calling
``_bootstrap_venv`` or ``_reexec_into_venv``, and the alias step must
target the current env's ``memory-talk`` script (not the dedicated
~/.memory-talk/.venv one).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path


async def _noop_validate(cfg):
    return None


def test_optout_keeps_current_env(setup_env, monkeypatch):
    from memorytalk.cli import setup as setup_pkg
    from memorytalk.cli.setup import wizard as wizard_mod
    from memorytalk.cli.setup.steps import embedding as embedding_step

    # Force the entry point to take the "not in dedicated venv" branch.
    monkeypatch.setattr(setup_pkg, "_already_in_venv", lambda: False)

    # Track that bootstrap + execv are NOT triggered when the user says 'n'.
    calls: dict = {"bootstrap": 0, "reexec": 0, "alias_arg": None}

    def fake_bootstrap():
        calls["bootstrap"] += 1
    def fake_reexec():
        calls["reexec"] += 1

    monkeypatch.setattr(setup_pkg, "_bootstrap_venv", fake_bootstrap)
    monkeypatch.setattr(setup_pkg, "_reexec_into_venv", fake_reexec)

    # Capture what _step_alias gets called with.
    def capturing_alias(memory_talk_bin: Path) -> dict:
        calls["alias_arg"] = memory_talk_bin
        return {
            "status": "noop",
            "link_path": str(memory_talk_bin.parent / "memory.talk"),
            "target": str(memory_talk_bin),
        }
    monkeypatch.setattr(wizard_mod, "_step_alias", capturing_alias)

    # Skip the embedder probe (we're using local provider).
    monkeypatch.setattr(embedding_step, "validate_embedder", _noop_validate)

    answers = "\n".join([
        "n",        # bootstrap dedicated venv? → no, keep current env
        "local",    # embedding provider
        "",         # model default
        "",         # dim default
        # vector / relation single-option auto-pick — no input consumed
        "",         # port default
        "n",        # don't start server
    ]) + "\n"

    result = setup_env.runner.invoke(setup_env.main, ["setup"], input=answers)

    assert result.exit_code == 0, (result.stdout, result.exception)

    # No bootstrap, no execv.
    assert calls["bootstrap"] == 0
    assert calls["reexec"] == 0

    # Alias targeted the *current* env, not ~/.memory-talk/.venv.
    expected_bin = Path(sys.executable).parent / "memory-talk"
    assert calls["alias_arg"] == expected_bin
    dedicated_venv = setup_env.fake_home / ".memory-talk" / ".venv"
    assert dedicated_venv not in calls["alias_arg"].parents

    # Settings still landed under fake HOME (data_root is independent of env).
    data = json.loads((setup_env.data_root / "settings.json").read_text())
    assert data["embedding"]["provider"] == "local"

    # Summary's `env` row reflects the current env's prefix, not the dedicated venv.
    assert str(Path(sys.executable).parent.parent) in result.stdout
    assert str(dedicated_venv) not in result.stdout

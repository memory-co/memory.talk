"""Opt-out path: user picks 'no' on the bootstrap prompt.

The wizard must run in the *current* python env without ever calling
``_bootstrap_venv`` or ``_reexec_into_venv``, and the PATH-takeover
step must be invoked with the current env's ``memory-talk`` script as
its target (not the dedicated ~/.memory-talk/.venv one).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path


async def _noop_validate(cfg):
    return None


def test_optout_keeps_current_env(setup_env, monkeypatch):
    from memorytalk.cli import setup as setup_pkg
    from memorytalk.cli.setup.steps import embedding as embedding_step

    # Force the entry point to take the "not in dedicated venv" branch.
    monkeypatch.setattr(setup_pkg, "_already_in_venv", lambda: False)

    # Track that bootstrap + execv are NOT triggered when the user says 'no'.
    calls: dict = {"bootstrap": 0, "reexec": 0, "takeover_arg": None}

    def fake_bootstrap():
        calls["bootstrap"] += 1
    def fake_reexec():
        calls["reexec"] += 1

    monkeypatch.setattr(setup_pkg, "_bootstrap_venv", fake_bootstrap)
    monkeypatch.setattr(setup_pkg, "_reexec_into_venv", fake_reexec)

    # Capture what _step_path_takeover gets called with. After the
    # restructure, takeover is invoked from the setup entry point
    # (``setup_pkg``), not from the wizard.
    def capturing_takeover(memory_talk_bin: Path) -> dict:
        calls["takeover_arg"] = memory_talk_bin
        return {"target": str(memory_talk_bin), "actions": []}
    monkeypatch.setattr(setup_pkg, "_step_path_takeover", capturing_takeover)

    # Skip the embedder probe (we're using local provider).
    monkeypatch.setattr(embedding_step, "validate_embedder", _noop_validate)

    setup_env.prompts.extend([
        "no",                   # bootstrap select → keep current env
        "local",                # provider select
        "all-MiniLM-L6-v2",     # model select (dim 384 auto)
        "",                     # port text → default
        "no",                   # start server select → don't start
    ])

    result = setup_env.runner.invoke(setup_env.main, ["setup"])

    assert result.exit_code == 0, (result.stdout, result.exception)

    # No bootstrap, no execv.
    assert calls["bootstrap"] == 0
    assert calls["reexec"] == 0

    # PATH takeover targeted the *current* env, not ~/.memory-talk/.venv.
    expected_bin = Path(sys.executable).parent / "memory-talk"
    assert calls["takeover_arg"] == expected_bin
    dedicated_venv = setup_env.fake_home / ".memory-talk" / ".venv"
    assert dedicated_venv not in calls["takeover_arg"].parents

    # Settings still landed under fake HOME (data_root is independent of env).
    data = json.loads((setup_env.data_root / "settings.json").read_text())
    assert data["embedding"]["provider"] == "local"

    # Summary's `env` row reflects the current env's prefix, not the dedicated venv.
    assert str(Path(sys.executable).parent.parent) in result.stdout
    assert str(dedicated_venv) not in result.stdout

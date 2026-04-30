"""Shared fixtures for in-process `memory-talk setup` tests.

Setup's first action is to bootstrap a venv at ``~/.memory-talk/.venv``
and re-exec into it. For the **wizard** tests we don't want either of
those to actually happen (real venv creation is slow + would write to
the dev's real home, and os.execv would replace pytest itself). So this
fixture stubs them out.

Patch sites map to where each name is *resolved at call time*, not where
it's defined:

- ``_already_in_venv`` / ``_bootstrap_venv`` / ``_reexec_into_venv``:
  the click entry point in ``memorytalk.cli.setup`` imports them into
  its own namespace, so we patch them on the package itself.
- ``start_server_proc`` / ``stop_server_proc`` / ``pid_alive``: called
  inside ``_step_server`` which lives in
  ``memorytalk.cli.setup.steps.server``.
- ``_step_alias``: called inside ``_wizard`` in
  ``memorytalk.cli.setup.wizard``.

The bootstrap path itself is exercised by a separate scenario,
``tests/cli/setup/test_bootstrap_real_venv``, which spins up a real
outer venv via subprocess.
"""
from __future__ import annotations
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from memorytalk.cli import main


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    runner = CliRunner()

    class Env:
        pass

    env = Env()
    env.fake_home = fake_home
    env.data_root = fake_home / ".memory-talk"   # Config(_data_root()) default
    env.runner = runner
    env.main = main

    from memorytalk.cli import setup as setup_pkg
    from memorytalk.cli.setup import wizard as wizard_mod
    from memorytalk.cli.setup.steps import server as server_step

    # Pretend we're already inside the venv → skip bootstrap entirely.
    monkeypatch.setattr(setup_pkg, "_already_in_venv", lambda: True)
    monkeypatch.setattr(setup_pkg, "_bootstrap_venv", lambda: None)
    monkeypatch.setattr(setup_pkg, "_reexec_into_venv", lambda: None)

    # Neutralize server lifecycle (called from setup.steps.server).
    monkeypatch.setattr(
        server_step, "start_server_proc",
        lambda cfg: {"status": "started", "pid": 99999, "port": cfg.settings.server.port},
    )
    monkeypatch.setattr(
        server_step, "stop_server_proc",
        lambda cfg: {"status": "stopped", "pid": 99999},
    )
    monkeypatch.setattr(server_step, "pid_alive", lambda pid: False)

    # Skip the symlink write — `_step_alias` is called from setup.wizard.
    # Signature is `_step_alias(memory_talk_bin)`; absorb whatever's passed.
    monkeypatch.setattr(
        wizard_mod, "_step_alias",
        lambda *a, **kw: {
            "status": "noop", "link_path": "/tmp/memory.talk", "target": "/tmp/memory-talk",
        },
    )

    def mock_openai_probe(dim: int = 1024) -> None:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * dim}]}
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=resp)
        from memorytalk.provider import embedding as emb_mod
        monkeypatch.setattr(emb_mod.httpx, "AsyncClient", lambda *a, **kw: client)

    env.mock_openai_probe = mock_openai_probe
    return env

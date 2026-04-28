"""Shared fixtures for `memory-talk setup` tests.

`setup_env` provides:
- a tmp data_root
- a CliRunner
- a `mock_openai_probe` helper that monkey-patches httpx.AsyncClient so
  the openai embedding probe in `validate_embedder` returns a
  configurable-dim vector without hitting the real network
- a `decline_server_start` toggle so tests don't actually spawn uvicorn
  unless they want to (the symlink step also needs `memory-talk` on
  PATH; in a CliRunner the binary may not be installed system-wide,
  so by default we mock both server and symlink steps)
"""
from __future__ import annotations
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from memorytalk.cli import main


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    data_root = tmp_path / ".mt"
    runner = CliRunner()

    class Env:
        pass

    env = Env()
    env.data_root = data_root
    env.runner = runner
    env.main = main

    # By default, neutralize the server start/stop and symlink steps so a
    # plain test doesn't accidentally spawn uvicorn or try to write into
    # /usr/bin. Tests that want real lifecycle behavior can override.
    from memorytalk.cli import setup as setup_module
    monkeypatch.setattr(
        setup_module, "start_server_proc",
        lambda cfg: {"status": "started", "pid": 99999, "port": cfg.settings.server.port},
    )
    monkeypatch.setattr(
        setup_module, "stop_server_proc",
        lambda cfg: {"status": "stopped", "pid": 99999},
    )
    monkeypatch.setattr(
        setup_module, "pid_alive", lambda pid: False,
    )
    monkeypatch.setattr(
        setup_module, "_step_alias",
        lambda install_mode: {
            "status": "noop", "link_path": "/tmp/memory.talk", "target": "/tmp/memory-talk",
        },
    )

    def mock_openai_probe(dim: int = 1024) -> None:
        """Patch httpx.AsyncClient so /v1/embeddings returns a `dim`-d vector."""
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

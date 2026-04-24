"""Shared fixture for sync scenarios: run the real CLI, route httpx through ASGI.

Tests drive the real `memory-talk` CLI via Click's `CliRunner`. The CLI's
httpx client factory is monkey-patched to return a FastAPI `TestClient`
that routes requests into the in-process ASGI app — no uvicorn subprocess,
no TCP socket. The TestClient is entered as a context manager so the
app's async lifespan runs (wiring services onto app.state) and exits
cleanly after all CLI invocations.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from memory_talk_v2.api import create_app
from memory_talk_v2.cli import _http, main


@pytest.fixture
def cli_env(dummy_config, monkeypatch):
    app = create_app(dummy_config)
    with TestClient(app, raise_server_exceptions=True) as shared_client:
        def _asgi_factory(cfg):
            return shared_client

        monkeypatch.setattr(_http, "_make_client", _asgi_factory)

        class Env:
            pass

        env = Env()
        env.runner = CliRunner()
        env.main = main
        env.app = app
        env.config = dummy_config
        yield env

"""Shared fixture for sync scenarios: run the real CLI, route httpx through ASGI.

Tests drive the real `memory-talk` CLI via Click's `CliRunner`. The CLI's
httpx client factory is monkey-patched to use `httpx.ASGITransport(app=app)`
so requests go directly into the in-process FastAPI app — no uvicorn
subprocess, no TCP socket. Everything else (Click arg parsing, adapter
dispatch, httpx serialization, FastAPI routing, Pydantic validation,
services, SQLite, LanceDB, filesystem) runs for real.
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
    # FastAPI's TestClient is an httpx.Client subclass that routes requests
    # through the ASGI app in-process with proper sync/async bridging.
    # We share a single instance across all CLI api() calls; we deliberately
    # don't use it as a context manager (that would trigger lifespan shutdown
    # and close the DB connection between CLI invocations).
    shared_client = TestClient(app, raise_server_exceptions=True)

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
    return env

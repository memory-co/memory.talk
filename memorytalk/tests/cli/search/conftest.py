"""Search-layer fixtures.

Adds `openai_cli_env` — same ASGI-routed CLI env as the default `cli_env`
from tests/cli/conftest.py, but configured with a real OpenAI-compatible
embedding provider (DashScope) instead of dummy.

Requires env var QWEN_KEY to be set. Without it, app lifespan startup
raises EmbedderValidationError and the fixture setup fails — which is
intentional: with-embedding search is supposed to fail hard when the
credential isn't available, matching the policy used in
tests/cli/server/test_openai_embedding_start/.
"""
from __future__ import annotations
import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from memorytalk.api import create_app
from memorytalk.cli import _http, main
from memorytalk.config import Config


@pytest.fixture
def openai_cli_env(tmp_data_root, monkeypatch):
    (tmp_data_root / "settings.json").write_text(
        json.dumps({
            "embedding": {
                "provider": "openai",
                "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
                "auth_env_key": "QWEN_KEY",
                "model": "text-embedding-v4",
                "dim": 1024,
            },
            "ttl": {
                "card": {"initial": 3600, "factor": 2.0, "max": 86400},
                "link": {"initial": 1800, "factor": 2.0, "max": 43200},
            },
        })
    )
    cfg = Config(tmp_data_root)

    app = create_app(cfg)
    with TestClient(app, raise_server_exceptions=True) as shared_client:
        monkeypatch.setattr(_http, "_make_client", lambda c: shared_client)

        class Env:
            pass

        env = Env()
        env.runner = CliRunner()
        env.main = main
        env.app = app
        env.config = cfg
        yield env

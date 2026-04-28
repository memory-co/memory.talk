"""Shared pytest fixtures for v2 tests."""
from __future__ import annotations
from pathlib import Path

import pytest

from memorytalk.config import Config


@pytest.fixture
def tmp_data_root(tmp_path: Path) -> Path:
    d = tmp_path / ".memory-talk"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def dummy_config(tmp_data_root: Path) -> Config:
    (tmp_data_root / "settings.json").write_text(
        '{"embedding": {"provider": "dummy", "dim": 384},'
        ' "ttl": {"card": {"initial": 3600, "factor": 2.0, "max": 86400},'
        '         "link": {"initial": 1800, "factor": 2.0, "max": 43200}}}'
    )
    return Config(tmp_data_root)


@pytest.fixture
def app_client(dummy_config: Config):
    """TestClient context manager drives async lifespan startup/shutdown."""
    from fastapi.testclient import TestClient
    from memorytalk.api import create_app
    app = create_app(dummy_config)
    with TestClient(app) as client:
        yield client

"""Fixtures for v3_insight_rename searchbase tests."""
from __future__ import annotations

import pytest

from memorytalk.config import Config
from memorytalk.provider.embedding import get_embedder
from memorytalk.searchbase import LocalSearchBackend


@pytest.fixture
async def backend(data_root):
    """Local searchbase with a single plain ``cards`` collection.

    Mirrors the ``backend`` fixture from tests/searchbase/local/conftest.py
    so migration tests can drive AdminBackend without importing from there.
    """
    config = Config(data_root)
    config.ensure_dirs()
    b = await LocalSearchBackend.create(
        data_dir=config.vectors_dir,
        dim=config.settings.embedding.dim,
        embedder=get_embedder(config),
        collections={"cards": {"fields": {}}},
    )
    try:
        yield b
    finally:
        await b.close()

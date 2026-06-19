"""Fixtures for v4_card_tables searchbase tests."""
from __future__ import annotations

import pytest

from memorytalk.config import Config
from memorytalk.provider.embedding import get_embedder
from memorytalk.searchbase import LocalSearchBackend


@pytest.fixture
async def backend(data_root):
    """Local searchbase seeded with the post-v3 collections (insights /
    rounds) but WITHOUT the v4 cards / positions — so a test can prove
    migration v4 creates them."""
    config = Config(data_root)
    config.ensure_dirs()
    b = await LocalSearchBackend.create(
        data_dir=config.vectors_dir,
        dim=config.settings.embedding.dim,
        embedder=get_embedder(config),
        collections={"insights": {"fields": {}},
                     "rounds": {"fields": {"session_id": "str"}}},
    )
    try:
        yield b
    finally:
        await b.close()

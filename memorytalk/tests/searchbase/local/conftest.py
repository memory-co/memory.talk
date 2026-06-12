"""Shared fixtures for searchbase/local scenarios.

Scenarios that just need "give me a working backend with one cards
collection" use ``backend``. Scenarios that drive Maintenance directly
(periodic_compaction / emfile_recovery) use ``index`` for a raw
CollectionIndex they can pair with their own Maintenance instance.
Scenarios with non-standard collection shapes (auto_split, declared
fields) build their own via ``make_backend`` / ``Config(data_root)``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from memorytalk.config import Config
from memorytalk.provider.embedding import get_embedder
from memorytalk.searchbase import LocalSearchBackend
from memorytalk.searchbase.local.index import CollectionIndex


async def make_backend(
    config,
    *,
    collections,
    max_text_length: int = 100_000,
    compact_interval_seconds: float | None = None,
    log_dir: Path | None = None,
):
    """Helper for scenarios that need a custom-shaped backend.

    Scenarios import this and call it with their own collection spec —
    rather than the ``backend`` fixture which hard-codes a plain
    ``cards`` collection.
    """
    kwargs = dict(
        data_dir=config.vectors_dir,
        dim=config.settings.embedding.dim,
        embedder=get_embedder(config),
        collections=collections,
        max_text_length=max_text_length,
    )
    if compact_interval_seconds is not None:
        kwargs["compact_interval_seconds"] = compact_interval_seconds
    if log_dir is not None:
        kwargs["log_dir"] = log_dir
    return await LocalSearchBackend.create(**kwargs)


@pytest.fixture
async def backend(data_root):
    """Standard backend with a single plain ``cards`` collection.

    Used by scenarios that don't need a special schema or maintenance
    timing — basic_io, health smoke checks, etc."""
    config = Config(data_root)
    config.ensure_dirs()
    b = await make_backend(config, collections={"cards": {"fields": {}}})
    try:
        yield b
    finally:
        await b.close()


@pytest.fixture
async def index(data_root):
    """Raw CollectionIndex paired with a single ``things`` collection.

    Maintenance + EMFILE-recovery scenarios construct their OWN
    Maintenance against this index — that lets them drive
    ``compact_all()`` / ``recover_from_emfile()`` directly with a tuned
    interval, instead of going through ``LocalSearchBackend.create``
    which always starts a real (long-interval) maintenance loop.
    """
    data_dir = Path(data_root) / "local_index_test"
    idx = await CollectionIndex.create(
        data_dir, dim=4, collections={"things": {"fields": {}}},
    )
    yield idx
    try:
        await idx.db.close()
    except Exception:
        pass

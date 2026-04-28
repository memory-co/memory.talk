"""Service-layer test fixtures — real async SQLite + LanceDB + dummy embedder."""
from __future__ import annotations
from pathlib import Path

import pytest_asyncio

from memorytalk.config import Config
from memorytalk.provider.embedding import DummyEmbedder
from memorytalk.provider.lancedb import LanceStore
from memorytalk.provider.storage import LocalStorage
from memorytalk.repository import SQLiteStore
from memorytalk.service import (
    CardService, EventWriter, LinkService, RebuildService,
    SearchService, SessionService,
)


@pytest_asyncio.fixture
async def services(tmp_path: Path):
    data_root = tmp_path / ".mt"
    data_root.mkdir()
    (data_root / "settings.json").write_text(
        '{"embedding": {"provider": "dummy", "dim": 384},'
        ' "ttl": {"card": {"initial": 3600, "factor": 2.0, "max": 86400},'
        '         "link": {"initial": 1800, "factor": 2.0, "max": 43200}}}'
    )
    cfg = Config(data_root)
    cfg.ensure_dirs()
    storage = LocalStorage(cfg.data_root)
    db = await SQLiteStore.create(cfg.db_path, storage)
    vectors = await LanceStore.create(cfg.vectors_dir, dim=cfg.settings.embedding.dim)
    embedder = DummyEmbedder(dim=cfg.settings.embedding.dim)
    events = EventWriter(db)

    async def _events_for(object_id: str) -> list[dict]:
        if object_id.startswith("card_"):
            return await db.cards.read_events(object_id)
        if object_id.startswith("sess_"):
            s = await db.sessions.get(object_id)
            if s is None:
                return []
            return await db.sessions.read_events(s["source"], object_id)
        raise ValueError(f"unknown object prefix: {object_id}")

    class Bundle:
        pass

    b = Bundle()
    b.config = cfg
    b.storage = storage
    b.db = db
    b.vectors = vectors
    b.embedder = embedder
    b.events = events
    b.events_for = _events_for
    b.sessions = SessionService(config=cfg, db=db, vectors=vectors, events=events)
    b.cards = CardService(
        config=cfg, db=db, vectors=vectors, embedder=embedder, events=events,
    )
    b.links = LinkService(config=cfg, db=db, events=events)
    b.search = SearchService(
        config=cfg, db=db, vectors=vectors, embedder=embedder,
    )
    b.rebuild = RebuildService(
        config=cfg, db=db, vectors=vectors, embedder=embedder,
    )
    yield b
    await db.close()

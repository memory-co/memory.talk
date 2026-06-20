"""Shared fixtures for v4 CardService scenarios.

``cardsvc`` gives a CardService backed by a real SQLiteStore with the full
v4 schema (v3 insight infra + v4 card tables — so the sessions table the
service validates against exists), no searchbase (None → upserts skipped),
and a seeded session ``sess-test`` so source/cite validation passes.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from memorytalk.config import Config
from memorytalk.migrations.v3 import init_database as v4_init
from memorytalk.provider.storage import LocalStorage
from memorytalk.repository.store import SQLiteStore
from memorytalk.service.cards import CardService
from memorytalk.service.events import EventWriter
from memorytalk.service.card_read import V4ReadService
from memorytalk.service.card_search import V4SearchService

SEEDED_SESSION = "sess-test0001"
SEEDED_SESSION_2 = "sess-test0002"


@pytest.fixture
async def cardsvc(data_root):
    config = Config(data_root)
    config.ensure_dirs()
    conn = await SQLiteStore.open_connection(config.db_path)
    await v4_init.run(conn, data_root=None)   # v3 infra + v4 card tables
    storage = LocalStorage(config.data_root)
    db = SQLiteStore(conn, config.db_path, storage)
    for _sid in (SEEDED_SESSION, SEEDED_SESSION_2):
        await db.sessions.upsert(
            _sid, "claude-code", "/x",
            "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {}, 5, "r5",
        )
    svc = CardService(db=db, search=None, events=EventWriter(db))
    read = V4ReadService(db)
    search = V4SearchService(db, None)   # no backend → empty-query/DSL path
    try:
        yield SimpleNamespace(
            svc=svc, db=db, session=SEEDED_SESSION, session2=SEEDED_SESSION_2,
            read=read, search=search,
        )
    finally:
        await conn.close()

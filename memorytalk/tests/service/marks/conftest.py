"""SessionMarkService scenarios — full v4 schema + a REAL searchbase.

``marksvc`` gives a SessionMarkService backed by a live LocalSearchBackend
(dummy embedder) so the #…？ embed/collide miss-hit path actually runs, plus
a seeded session (``round_count=5``) the optimistic lock checks against.
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
from memorytalk.service.searchbase_schema import build_search_backend
from memorytalk.service.session_marks import SessionMarkService

SEEDED_SESSION = "sess-test0001"


@pytest.fixture
async def marksvc(data_root):
    config = Config(data_root)
    config.ensure_dirs()
    conn = await SQLiteStore.open_connection(config.db_path)
    await v4_init.run(conn, data_root=None)
    storage = LocalStorage(config.data_root)
    db = SQLiteStore(conn, config.db_path, storage)
    await db.sessions.upsert(
        SEEDED_SESSION, "claude-code", "/x",
        "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {}, 5, "r5",
    )
    search = await build_search_backend(config)
    events = EventWriter(db)
    cards = CardService(db=db, search=search, events=events)
    svc = SessionMarkService(db=db, search=search, cards=cards)
    try:
        yield SimpleNamespace(
            svc=svc, db=db, search=search, cards=cards, session=SEEDED_SESSION,
        )
    finally:
        await search.close()
        await conn.close()

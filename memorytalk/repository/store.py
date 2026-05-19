"""SQLiteStore — owns the aiosqlite connection + per-noun stores.

Each per-noun store does BOTH file ops (via the injected Storage) and
SQL ops (via aiosqlite). Services access them as::

    await db.sessions.write_meta(source, sid, meta)   # file
    await db.sessions.upsert(...)                      # SQL
    await db.cards.write_doc(card)                    # file
    await db.cards.insert(...)                         # SQL
    await db.reviews.insert(...)                      # SQL
"""
from __future__ import annotations
from pathlib import Path

import aiosqlite

from memorytalk.provider.storage import Storage
from memorytalk.repository.cards import CardStore
from memorytalk.repository.recall import RecallStore
from memorytalk.repository.reviews import ReviewStore
from memorytalk.repository.schema import init_schema
from memorytalk.repository.search_log import SearchLogStore
from memorytalk.repository.sessions import SessionStore


class SQLiteStore:
    def __init__(self, conn: aiosqlite.Connection, db_path: Path, storage: Storage):
        self.conn = conn
        self.db_path = db_path
        self.storage = storage
        self.sessions = SessionStore(conn, storage)
        self.cards = CardStore(conn, storage)
        self.reviews = ReviewStore(conn)
        self.search_log = SearchLogStore(conn)
        self.recall = RecallStore(conn)

    @classmethod
    async def create(cls, db_path: Path, storage: Storage) -> "SQLiteStore":
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        # PRAGMA foreign_keys=ON gates the FOREIGN KEY clauses in our schema.
        # SQLite default-off; we want referential integrity at the boundary.
        await conn.execute("PRAGMA foreign_keys = ON")
        await init_schema(conn)
        return cls(conn, db_path, storage)

    async def close(self) -> None:
        await self.conn.close()

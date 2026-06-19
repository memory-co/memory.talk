"""SQLiteStore — owns the aiosqlite connection + per-noun stores.

Each per-noun store does BOTH file ops (via the injected Storage) and
SQL ops (via aiosqlite). Services access them as::

    await db.sessions.write_meta(source, sid, meta)   # file
    await db.sessions.upsert(...)                      # SQL
    await db.cards.write_doc(card)                    # file
    await db.cards.insert(...)                         # SQL
"""
from __future__ import annotations
from pathlib import Path

import aiosqlite

from memorytalk.provider.storage import Storage
from memorytalk.repository.cards import CardStore
from memorytalk.repository.explores import ExploreStore
from memorytalk.repository.recall import RecallStore
from memorytalk.repository.search_log import SearchLogStore
from memorytalk.repository.sessions import SessionStore


class SQLiteStore:
    def __init__(self, conn: aiosqlite.Connection, db_path: Path, storage: Storage):
        self.conn = conn
        self.db_path = db_path
        self.storage = storage
        self.sessions = SessionStore(conn, storage)
        self.cards = CardStore(conn, storage)
        self.search_log = SearchLogStore(conn)
        self.recall = RecallStore(conn)
        self.explores = ExploreStore(conn)

    @classmethod
    async def open_connection(cls, db_path: Path) -> aiosqlite.Connection:
        """Open the raw aiosqlite connection + apply the PRAGMAs we
        always want. Schema setup is NOT done here — that's
        ``memorytalk.migration``'s job, and it runs against this same
        connection before the store is wrapped around it (see the
        lifespan in ``memorytalk.api``). Split out so callers that need
        to run migrations against the conn (the lifespan) and callers
        that just need a wrapped store (everything else) share the same
        open path."""
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        # PRAGMA foreign_keys=ON gates the FOREIGN KEY clauses in our
        # schema. SQLite default-off; we want referential integrity at
        # the boundary.
        await conn.execute("PRAGMA foreign_keys = ON")
        return conn

    async def close(self) -> None:
        await self.conn.close()

"""SQLiteStore — owns the aiosqlite connection + per-noun stores.

Each per-noun store does BOTH file ops (via the injected Storage) and
SQL ops (via aiosqlite). Services access them as::

    await db.sessions.write_meta(source, sid, meta)   # file
    await db.sessions.upsert(...)                      # SQL
    await db.cards.write_doc(card)                     # file (v4 card)
    await db.cards.insert(...)                          # SQL
"""
from __future__ import annotations
from pathlib import Path

import aiosqlite

from memorytalk.provider.storage import Storage
from memorytalk.repository.insights import InsightStore
from memorytalk.repository.explores import ExploreStore
from memorytalk.repository.recall import RecallStore
from memorytalk.repository.search_log import SearchLogStore
from memorytalk.repository.sessions import SessionStore
from memorytalk.repository.cards import CardStore
from memorytalk.repository.positions import PositionStore
from memorytalk.repository.reviews import ReviewStore
from memorytalk.repository.card_links import CardLinkStore
from memorytalk.repository.card_sessions import CardSessionStore
from memorytalk.repository.position_sessions import PositionSessionStore
from memorytalk.repository.link_sessions import LinkSessionStore
from memorytalk.repository.session_marks import SessionMarkStore
from memorytalk.repository.session_mark_files import SessionMarkFileStore


class SQLiteStore:
    def __init__(self, conn: aiosqlite.Connection, db_path: Path, storage: Storage):
        self.conn = conn
        self.db_path = db_path
        self.storage = storage
        self.sessions = SessionStore(conn, storage)
        self.insights = InsightStore(conn, storage)
        self.search_log = SearchLogStore(conn)
        self.recall = RecallStore(conn)
        self.explores = ExploreStore(conn)
        # v4 card subsystem (governed question graph). Coexists with the
        # v3 ``insights`` stores; separate tables, no FK between them.
        self.cards = CardStore(conn, storage)
        self.positions = PositionStore(conn, storage)
        self.reviews = ReviewStore(conn)
        self.card_links = CardLinkStore(conn, storage)
        self.card_sessions = CardSessionStore(conn)
        self.position_sessions = PositionSessionStore(conn)
        self.link_sessions = LinkSessionStore(conn)
        self.session_marks = SessionMarkStore(conn)
        self.session_mark_files = SessionMarkFileStore(storage)

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

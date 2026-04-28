"""SQLiteStore — owns the aiosqlite connection + per-noun stores.

Each per-noun store now does BOTH file ops (via the injected Storage) and
SQL ops (via aiosqlite). Services access them as:
  await db.sessions.write_meta(source, sid, meta)   # file
  await db.sessions.upsert(...)                      # SQL
  await db.cards.write_doc(card)                    # file
  await db.cards.insert(...)                         # SQL
  await db.search_log.record(rec, now=...)          # file + SQL combined
"""
from __future__ import annotations
from pathlib import Path

import aiosqlite

from memory_talk_v2.provider.storage import Storage
from memory_talk_v2.repository.cards import CardStore
from memory_talk_v2.repository.links import LinkStore
from memory_talk_v2.repository.schema import init_schema
from memory_talk_v2.repository.search_log import SearchLogStore
from memory_talk_v2.repository.sessions import SessionStore


class SQLiteStore:
    def __init__(self, conn: aiosqlite.Connection, db_path: Path, storage: Storage):
        self.conn = conn
        self.db_path = db_path
        self.storage = storage
        self.sessions = SessionStore(conn, storage)
        self.cards = CardStore(conn, storage)
        self.links = LinkStore(conn, storage)
        self.search_log = SearchLogStore(conn, storage)

    @classmethod
    async def create(cls, db_path: Path, storage: Storage) -> "SQLiteStore":
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await init_schema(conn)
        return cls(conn, db_path, storage)

    async def close(self) -> None:
        await self.conn.close()

    async def clear_all(self) -> None:
        """Used by /v2/rebuild — drop all v2 table contents."""
        for t in ("search_log", "links", "cards", "rounds", "sessions"):
            await self.conn.execute(f"DELETE FROM {t}")
        await self.conn.commit()

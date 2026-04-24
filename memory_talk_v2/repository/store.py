"""SQLiteStore — owns the aiosqlite connection and bundles per-noun repos.

Services inject `db: SQLiteStore` and access repos as attributes:
  await db.sessions.get(sid)
  await db.cards.insert(...)
  await db.links.touching(oid)
  await db.search_log.insert(...)
"""
from __future__ import annotations
from pathlib import Path

import aiosqlite

from memory_talk_v2.repository.cards import CardRepo
from memory_talk_v2.repository.links import LinkRepo
from memory_talk_v2.repository.schema import init_schema
from memory_talk_v2.repository.search_log import SearchLogRepo
from memory_talk_v2.repository.sessions import SessionRepo


class SQLiteStore:
    def __init__(self, conn: aiosqlite.Connection, db_path: Path):
        self.conn = conn
        self.db_path = db_path
        self.sessions = SessionRepo(conn)
        self.cards = CardRepo(conn)
        self.links = LinkRepo(conn)
        self.search_log = SearchLogRepo(conn)

    @classmethod
    async def create(cls, db_path: Path) -> "SQLiteStore":
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so FastAPI can call from threadpool workers.
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await init_schema(conn)
        return cls(conn, db_path)

    async def close(self) -> None:
        await self.conn.close()

    async def clear_all(self) -> None:
        """Used by /v2/rebuild — drop all v2 table contents."""
        for t in ("search_log", "links", "cards", "rounds", "sessions"):
            await self.conn.execute(f"DELETE FROM {t}")
        await self.conn.commit()

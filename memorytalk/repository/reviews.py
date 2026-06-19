"""ReviewStore -- stances on a Position (argument in {-1,0,1}).

SQLite-only here; the file mirror (reviews appended under the card dir)
is wired in the service plan alongside the annotation write path.
No FOREIGN KEY on position_id. card_id is the redundant cache
(= positions.card_id); the service backfills it from position_id.
"""
from __future__ import annotations

import aiosqlite


class ReviewStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, review_id: str, position_id: str, card_id: str, session_id: str,
        indexes: str, argument: int, comment: str | None, created_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO reviews "
            "(review_id, position_id, card_id, session_id, indexes, argument, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (review_id, position_id, card_id, session_id, indexes, argument, comment, created_at),
        )
        await self.conn.commit()

    async def exists(self, review_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM reviews WHERE review_id = ?", (review_id,),
        ) as cur:
            return await cur.fetchone() is not None

    async def list_for_position(self, position_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM reviews WHERE position_id = ? ORDER BY created_at DESC",
            (position_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM reviews") as cur:
            return (await cur.fetchone())[0]

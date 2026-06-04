"""ReviewStore — reviews are SQLite-primary; the file mirror lives next to
the parent card (handled by ``CardStore.append_review_mirror``)."""
from __future__ import annotations

import aiosqlite


class ReviewStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self,
        review_id: str,
        card_id: str,
        session_id: str,
        indexes: str,
        score: int,
        comment: str | None,
        created_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO reviews "
            "(review_id, card_id, session_id, indexes, score, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (review_id, card_id, session_id, indexes, score, comment, created_at),
        )
        await self.conn.commit()

    async def exists(self, review_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM reviews WHERE review_id = ?", (review_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def list_for_card(self, card_id: str) -> list[dict]:
        """Reviews of a card, newest first (matches the read-response contract)."""
        async with self.conn.execute(
            "SELECT review_id, card_id, session_id, indexes, score, comment, created_at "
            "FROM reviews WHERE card_id = ? ORDER BY created_at DESC",
            (card_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def delete_for_card(self, card_id: str) -> int:
        """Delete all reviews of a card. Returns the number of rows
        removed (so the service layer can report it in the response).

        Used by ``CardService.delete``; reviews-of-a-deleted-card make
        no sense and ``reviews.card_id`` FK has no ON DELETE CASCADE."""
        async with self.conn.execute(
            "DELETE FROM reviews WHERE card_id = ?", (card_id,),
        ) as cursor:
            n = cursor.rowcount
        await self.conn.commit()
        return n

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM reviews") as cursor:
            row = await cursor.fetchone()
        return row[0]

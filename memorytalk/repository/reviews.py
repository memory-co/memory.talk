"""ReviewStore -- stances on a Position or a CardLink (argument in {-1,0,1}).

SQLite-only here (review has its own canonical, not the card's immutable
core). A review targets ``card_id#<target>`` where ``target`` = a Position
seq ('p<n>') or a CardLink seq ('l<n>'); ``target_kind`` ('position' |
'link') is derived from the seq prefix. No FOREIGN KEY on target.
"""
from __future__ import annotations

import aiosqlite

from memorytalk.util.ids import LINK_SEQ_PREFIX, POSITION_SEQ_PREFIX


def target_kind_of(target: str) -> str:
    """Derive 'position' | 'link' from a card-scoped target seq."""
    if target.startswith(POSITION_SEQ_PREFIX):
        return "position"
    if target.startswith(LINK_SEQ_PREFIX):
        return "link"
    raise ValueError(f"unknown review target seq: {target!r}")


class ReviewStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, review_id: str, card_id: str, target: str, target_kind: str,
        session_id: str, indexes: str, argument: int, comment: str | None,
        created_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO reviews "
            "(review_id, card_id, target, target_kind, session_id, indexes, "
            " argument, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (review_id, card_id, target, target_kind, session_id, indexes,
             argument, comment, created_at),
        )
        await self.conn.commit()

    async def exists(self, review_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM reviews WHERE review_id = ?", (review_id,),
        ) as cur:
            return await cur.fetchone() is not None

    async def list_for_target(self, card_id: str, target: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM reviews WHERE card_id = ? AND target = ? "
            "ORDER BY created_at DESC",
            (card_id, target),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_for_card(self, card_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM reviews WHERE card_id = ? ORDER BY created_at DESC",
            (card_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM reviews") as cur:
            return (await cur.fetchone())[0]

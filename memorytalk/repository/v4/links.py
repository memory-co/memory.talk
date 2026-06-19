"""CardLinkStore -- card<->card IBIS edges (card_links).

A row = subject ``card_id`` + ``type`` + ``target_id`` (NOT symmetric
from/to). ``target_type`` ('card' | 'position') is derived from the
target_id prefix and stored for filtering. Idempotent on the PK
(card_id, type, target_id). No FOREIGN KEY -- targets may dangle.
"""
from __future__ import annotations

import aiosqlite


def _target_type(target_id: str) -> str:
    if target_id.startswith("pos_"):
        return "position"
    return "card"


class CardLinkStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, card_id: str, type_: str, target_id: str, created_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO card_links "
            "(card_id, type, target_id, target_type, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (card_id, type_, target_id, _target_type(target_id), created_at),
        )
        await self.conn.commit()

    async def list_out(self, card_id: str) -> list[dict]:
        """Edges where this card is the subject."""
        async with self.conn.execute(
            "SELECT * FROM card_links WHERE card_id = ? ORDER BY created_at ASC",
            (card_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_in(self, target_id: str) -> list[dict]:
        """Edges pointing at this id (reverse lookup, idx_v4_links_target)."""
        async with self.conn.execute(
            "SELECT * FROM card_links WHERE target_id = ? ORDER BY created_at ASC",
            (target_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

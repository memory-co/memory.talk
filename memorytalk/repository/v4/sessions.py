"""CardSessionStore -- card<->session provenance (card_sessions).

Records where a card / position came from. Multi-session per card. No own
id; composite PK (card_id, session_id, position_id), idempotent re-insert
via INSERT OR IGNORE. position_id "" = card-level association. No FOREIGN
KEY. The canonical of this relation is the per-round annotation
(questions[]); this table is its derived index (see session-annotation.md).
"""
from __future__ import annotations

import aiosqlite


class CardSessionStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, card_id: str, session_id: str, position_id: str = "",
        indexes: str = "[]", created_at: str = "",
    ) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO card_sessions "
            "(card_id, session_id, position_id, indexes, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (card_id, session_id, position_id, indexes, created_at),
        )
        await self.conn.commit()

    async def list_for_card(self, card_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM card_sessions WHERE card_id = ? ORDER BY created_at ASC",
            (card_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_cards_for_session(self, session_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM card_sessions WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

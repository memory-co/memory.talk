"""CardSessionStore -- card<->session provenance, via mark (card_sessions).

Records which mark of which session created/connected this card -- a
card-level (issue-level) provenance edge, granular to the mark. No own id;
composite PK (card_id, session_id, mark), idempotent re-insert via INSERT
OR IGNORE. Same card<->session may have several rows (different marks). No
FOREIGN KEY. Canonical is the per-mark ``issues[]`` in marks/m<n>.yaml;
this table is its derived index.
"""
from __future__ import annotations

import aiosqlite


class CardSessionStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, card_id: str, session_id: str, mark: str,
        indexes: str, created_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO card_sessions "
            "(card_id, session_id, mark, indexes, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (card_id, session_id, mark, indexes, created_at),
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

    async def list_cards_for_mark(self, session_id: str, mark: str) -> list[dict]:
        """Reverse lookup: which cards a specific mark (sess#m<n>) made/linked."""
        async with self.conn.execute(
            "SELECT * FROM card_sessions WHERE session_id = ? AND mark = ? "
            "ORDER BY created_at ASC",
            (session_id, mark),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

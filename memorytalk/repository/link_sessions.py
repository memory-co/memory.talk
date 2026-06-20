"""LinkSessionStore -- link<->session provenance (link_sessions).

Records which rounds (``indexes``) of which session a CardLink (IBIS edge)
was observed / grounded in. No own id; composite PK (card_id, link,
session_id), idempotent via INSERT OR IGNORE. No FOREIGN KEY. Mirrors
``position_sessions`` (the edge's evidence provenance).
"""
from __future__ import annotations

import aiosqlite


class LinkSessionStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, card_id: str, link: str, session_id: str,
        indexes: str, created_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO link_sessions "
            "(card_id, link, session_id, indexes, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (card_id, link, session_id, indexes, created_at),
        )
        await self.conn.commit()

    async def list_for_link(self, card_id: str, link: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM link_sessions WHERE card_id = ? AND link = ? "
            "ORDER BY created_at ASC",
            (card_id, link),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_links_for_session(self, session_id: str) -> list[dict]:
        """Reverse lookup: which edges a session surfaced."""
        async with self.conn.execute(
            "SELECT * FROM link_sessions WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

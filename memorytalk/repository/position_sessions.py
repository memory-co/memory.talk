"""PositionSessionStore -- position<->session provenance (position_sessions).

Records which rounds (``indexes``) of which session an answer (Position)
grew out of; ``mark`` is optional ('' = round-only). No own id; composite
PK (card_id, position, session_id, mark), idempotent via INSERT OR IGNORE.
No FOREIGN KEY. Canonical is the Position's ``--source`` annotations; this
SQLite table is the joinable derived index.
"""
from __future__ import annotations

import aiosqlite


class PositionSessionStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, card_id: str, position: str, session_id: str,
        indexes: str, created_at: str, *, mark: str = "",
    ) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO position_sessions "
            "(card_id, position, session_id, indexes, mark, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (card_id, position, session_id, indexes, mark, created_at),
        )
        await self.conn.commit()

    async def list_for_position(self, card_id: str, position: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM position_sessions WHERE card_id = ? AND position = ? "
            "ORDER BY created_at ASC",
            (card_id, position),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_positions_for_session(self, session_id: str) -> list[dict]:
        """Reverse lookup: which answers a session inspired."""
        async with self.conn.execute(
            "SELECT * FROM position_sessions WHERE session_id = ? "
            "ORDER BY created_at ASC",
            (session_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

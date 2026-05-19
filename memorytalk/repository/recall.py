"""RecallStore — recall_log (session, card) pairs for dedup."""
from __future__ import annotations

import aiosqlite


class RecallStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def already_recalled(self, session_id: str, card_ids: list[str]) -> set[str]:
        """Return the subset of ``card_ids`` already in this session's recall_log."""
        if not card_ids:
            return set()
        placeholders = ",".join("?" * len(card_ids))
        async with self.conn.execute(
            f"SELECT card_id FROM recall_log WHERE session_id = ? "
            f"AND card_id IN ({placeholders})",
            [session_id, *card_ids],
        ) as cursor:
            rows = await cursor.fetchall()
        return {r[0] for r in rows}

    async def record(self, session_id: str, card_ids: list[str], now: str) -> None:
        if not card_ids:
            return
        rows = [(session_id, cid, now) for cid in card_ids]
        await self.conn.executemany(
            "INSERT OR IGNORE INTO recall_log (session_id, card_id, recalled_at) "
            "VALUES (?, ?, ?)",
            rows,
        )
        await self.conn.commit()

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM recall_log") as cursor:
            row = await cursor.fetchone()
        return row[0]

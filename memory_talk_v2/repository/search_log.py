"""SearchLogRepo — async append-only persistence for /v2/search audit records."""
from __future__ import annotations

import aiosqlite


class SearchLogRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, search_id: str, query: str, where_dsl: str | None,
        top_k: int, created_at: str, response_json: str,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO search_log (search_id, query, where_dsl, top_k, created_at, response_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (search_id, query, where_dsl, top_k, created_at, response_json),
        )
        await self.conn.commit()

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM search_log") as cursor:
            row = await cursor.fetchone()
        return row[0]

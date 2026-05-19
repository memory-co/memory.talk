"""SearchLogStore — append-only audit of every search response.

Stores the full response body so post-hoc audit can reconstruct what the
user saw at search-time even if the underlying data changes later.
"""
from __future__ import annotations
import json

import aiosqlite


class SearchLogStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self,
        search_id: str,
        query: str,
        where_dsl: str | None,
        top_k: int,
        created_at: str,
        response: dict,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO search_log "
            "(search_id, query, where_dsl, top_k, created_at, response_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (search_id, query, where_dsl, top_k, created_at,
             json.dumps(response, ensure_ascii=False)),
        )
        await self.conn.commit()

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM search_log") as cursor:
            row = await cursor.fetchone()
        return row[0]

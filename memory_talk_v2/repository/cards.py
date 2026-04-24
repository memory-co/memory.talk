"""CardRepo — async CRUD for cards table."""
from __future__ import annotations
import json

import aiosqlite


class CardRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self, card_id: str, summary: str, rounds: list[dict],
        created_at: str, expires_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO cards (card_id, summary, rounds, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (card_id, summary, json.dumps(rounds, ensure_ascii=False), created_at, expires_at),
        )
        await self.conn.commit()

    async def get(self, card_id: str) -> dict | None:
        async with self.conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "card_id": row["card_id"],
            "summary": row["summary"],
            "rounds": json.loads(row["rounds"] or "[]"),
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }

    async def update_expires_at(self, card_id: str, expires_at: str) -> None:
        await self.conn.execute(
            "UPDATE cards SET expires_at = ? WHERE card_id = ?", (expires_at, card_id),
        )
        await self.conn.commit()

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM cards") as cursor:
            row = await cursor.fetchone()
        return row[0]

    # ---------- search helpers ----------

    async def dsl_whitelist(self, where_sql: str, params: list) -> list[str]:
        async with self.conn.execute(
            f"SELECT card_id FROM cards WHERE {where_sql}", params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def metadata_filtered(self, whitelist: list[str] | None, top_k: int) -> list[dict]:
        sql = "SELECT card_id, summary, created_at FROM cards"
        params: list = []
        if whitelist is not None:
            placeholders = ",".join("?" * len(whitelist)) or "NULL"
            sql += f" WHERE card_id IN ({placeholders})"
            params.extend(whitelist)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(top_k)
        async with self.conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

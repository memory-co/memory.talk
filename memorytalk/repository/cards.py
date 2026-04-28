"""CardStore — card persistence (file layer + SQLite).

File layout:
  cards/<bucket>/<card_id>/card.json
  cards/<bucket>/<card_id>/events.jsonl
"""
from __future__ import annotations
import json
from typing import AsyncIterator

import aiosqlite

from memorytalk.provider.storage import Storage


class CardStore:
    PREFIX = "cards"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage):
        self.conn = conn
        self.storage = storage

    # ---------- file-layer keys ----------

    @staticmethod
    def _bucket(card_id: str) -> str:
        raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _doc_key(self, card_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/card.json"

    def _events_key(self, card_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/events.jsonl"

    # ---------- file-layer ops ----------

    async def write_doc(self, card: dict) -> None:
        await self.storage.write_text(
            self._doc_key(card["card_id"]),
            json.dumps(card, ensure_ascii=False, indent=2),
        )

    async def read_doc(self, card_id: str) -> dict | None:
        text = await self.storage.read_text(self._doc_key(card_id))
        return json.loads(text) if text else None

    async def append_event(self, card_id: str, event: dict) -> None:
        await self.storage.append_text(
            self._events_key(card_id),
            json.dumps(event, ensure_ascii=False) + "\n",
        )

    async def read_events(self, card_id: str) -> list[dict]:
        text = await self.storage.read_text(self._events_key(card_id))
        if not text:
            return []
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    async def iter_docs(self) -> AsyncIterator[dict]:
        keys = await self.storage.list_subkeys(self.PREFIX)
        for k in keys:
            if k.endswith("/card.json"):
                text = await self.storage.read_text(k)
                if text:
                    yield json.loads(text)

    # ---------- cards table ----------

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

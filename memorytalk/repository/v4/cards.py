"""V4CardStore -- card (==Issue) persistence: file canonical + SQLite index.

File layout::

    cards/<bucket>/<card_id>/card.json              (canonical: issue + created_at)
    cards/<bucket>/<card_id>/positions/<pid>.json   (written by PositionStore)

SQLite ``cards`` row mirrors issue + created_at and holds the redundant
position_count / link_count counters.
"""
from __future__ import annotations

import json

import aiosqlite

from memorytalk.provider.storage import Storage


class V4CardStore:
    PREFIX = "cards"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage):
        self.conn = conn
        self.storage = storage

    @staticmethod
    def _bucket(card_id: str) -> str:
        raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _doc_key(self, card_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/card.json"

    # -- file layer --
    async def write_doc(self, card: dict) -> None:
        await self.storage.write_text(
            self._doc_key(card["card_id"]),
            json.dumps(card, ensure_ascii=False, indent=2),
        )

    async def read_doc(self, card_id: str) -> dict | None:
        text = await self.storage.read_text(self._doc_key(card_id))
        return json.loads(text) if text else None

    # -- cards table --
    async def insert(self, card_id: str, issue: str, created_at: str) -> None:
        await self.conn.execute(
            "INSERT INTO cards (card_id, issue, created_at, position_count, link_count) "
            "VALUES (?, ?, ?, 0, 0)",
            (card_id, issue, created_at),
        )
        await self.conn.commit()

    async def get(self, card_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT card_id, issue, created_at, position_count, link_count "
            "FROM cards WHERE card_id = ?", (card_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return {
            "card_id": row["card_id"], "issue": row["issue"],
            "created_at": row["created_at"],
            "position_count": row["position_count"], "link_count": row["link_count"],
        }

    async def exists(self, card_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM cards WHERE card_id = ?", (card_id,),
        ) as cur:
            return await cur.fetchone() is not None

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM cards") as cur:
            return (await cur.fetchone())[0]

    async def bump_position_count(self, card_id: str, delta: int = 1) -> None:
        await self.conn.execute(
            "UPDATE cards SET position_count = position_count + ? WHERE card_id = ?",
            (delta, card_id),
        )
        await self.conn.commit()

    async def bump_link_count(self, card_id: str, delta: int = 1) -> None:
        await self.conn.execute(
            "UPDATE cards SET link_count = link_count + ? WHERE card_id = ?",
            (delta, card_id),
        )
        await self.conn.commit()

    async def list_cards(
        self, *, since: str | None = None, until: str | None = None, limit: int = 20,
    ) -> tuple[int, list[dict]]:
        clauses: list[str] = []
        params: list = []
        if since:
            clauses.append("created_at >= ?"); params.append(since)
        if until:
            clauses.append("created_at <= ?"); params.append(until)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        async with self.conn.execute(
            f"SELECT COUNT(*) FROM cards {where}", params,
        ) as cur:
            total = (await cur.fetchone())[0]
        async with self.conn.execute(
            f"SELECT card_id, issue, created_at, position_count, link_count "
            f"FROM cards {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ) as cur:
            rows = await cur.fetchall()
        return total, [dict(r) for r in rows]

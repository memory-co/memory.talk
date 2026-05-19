"""CardStore — card persistence (file layer + SQLite).

File layout::

    cards/<bucket>/<card_id>/card.json        (immutable payload mirror)
    cards/<bucket>/<card_id>/events.jsonl     (created / read / reviewed / recalled)
    cards/<bucket>/<card_id>/reviews.jsonl    (review mirror — full reviews appended)

The ``card_stats`` and ``card_source_cards`` tables hold runtime state +
edges; ``cards`` itself holds immutable payload (insight + rounds JSON).
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

    # ────────── file-layer keys ──────────

    @staticmethod
    def _bucket(card_id: str) -> str:
        raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _doc_key(self, card_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/card.json"

    def _events_key(self, card_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/events.jsonl"

    def _reviews_key(self, card_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/reviews.jsonl"

    # ────────── file-layer ops ──────────

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

    async def append_review_mirror(self, card_id: str, review: dict) -> None:
        await self.storage.append_text(
            self._reviews_key(card_id),
            json.dumps(review, ensure_ascii=False) + "\n",
        )

    async def iter_docs(self) -> AsyncIterator[dict]:
        keys = await self.storage.list_subkeys(self.PREFIX)
        for k in keys:
            if k.endswith("/card.json"):
                text = await self.storage.read_text(k)
                if text:
                    yield json.loads(text)

    # ────────── cards table ──────────

    async def insert(self, card_id: str, insight: str, rounds: list[dict], created_at: str) -> None:
        await self.conn.execute(
            "INSERT INTO cards (card_id, insight, rounds, created_at) VALUES (?, ?, ?, ?)",
            (card_id, insight, json.dumps(rounds, ensure_ascii=False), created_at),
        )
        await self.conn.commit()

    async def get(self, card_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM cards WHERE card_id = ?", (card_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "card_id": row["card_id"],
            "insight": row["insight"],
            "rounds": json.loads(row["rounds"] or "[]"),
            "created_at": row["created_at"],
        }

    async def exists(self, card_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM cards WHERE card_id = ?", (card_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM cards") as cursor:
            row = await cursor.fetchone()
        return row[0]

    # ────────── card_stats ──────────

    async def init_stats(self, card_id: str, now: str) -> None:
        """Insert a stats row for a freshly created card (all zeros)."""
        await self.conn.execute(
            "INSERT INTO card_stats "
            "(card_id, review_up, review_down, review_neutral, review_count, "
            " read_count, recall_count, updated_at) "
            "VALUES (?, 0, 0, 0, 0, 0, 0, ?)",
            (card_id, now),
        )
        await self.conn.commit()

    async def get_stats(self, card_id: str) -> dict:
        """Return the stats row (all zeros if missing — happens for tests that
        create card rows directly without the service)."""
        async with self.conn.execute(
            "SELECT review_up, review_down, review_neutral, review_count, "
            "read_count, recall_count FROM card_stats WHERE card_id = ?",
            (card_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return {
                "review_up": 0, "review_down": 0, "review_neutral": 0,
                "review_count": 0, "read_count": 0, "recall_count": 0,
            }
        return {
            "review_up": row["review_up"],
            "review_down": row["review_down"],
            "review_neutral": row["review_neutral"],
            "review_count": row["review_count"],
            "read_count": row["read_count"],
            "recall_count": row["recall_count"],
        }

    async def bump_read(self, card_id: str, now: str, delta: int = 1) -> None:
        await self.conn.execute(
            "UPDATE card_stats SET read_count = read_count + ?, updated_at = ? "
            "WHERE card_id = ?",
            (delta, now, card_id),
        )
        await self.conn.commit()

    async def bump_recall(self, card_id: str, now: str, delta: int = 1) -> None:
        await self.conn.execute(
            "UPDATE card_stats SET recall_count = recall_count + ?, updated_at = ? "
            "WHERE card_id = ?",
            (delta, now, card_id),
        )
        await self.conn.commit()

    async def bump_review(self, card_id: str, score: int, now: str) -> None:
        """Atomically increment review_count + the score-specific bucket."""
        if score == 1:
            col = "review_up"
        elif score == -1:
            col = "review_down"
        elif score == 0:
            col = "review_neutral"
        else:
            raise ValueError(f"score must be -1/0/1, got {score!r}")
        await self.conn.execute(
            f"UPDATE card_stats "
            f"SET {col} = {col} + 1, review_count = review_count + 1, updated_at = ? "
            f"WHERE card_id = ?",
            (now, card_id),
        )
        await self.conn.commit()

    # ────────── card_source_cards ──────────

    async def insert_source_cards(self, card_id: str, items: list[dict]) -> None:
        """Insert source_cards rows in declared order."""
        if not items:
            return
        rows = [
            (card_id, i, item["card_id"], item["relation"])
            for i, item in enumerate(items)
        ]
        await self.conn.executemany(
            "INSERT INTO card_source_cards "
            "(card_id, seq, source_card_id, relation) VALUES (?, ?, ?, ?)",
            rows,
        )
        await self.conn.commit()

    async def list_source_cards(self, card_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT source_card_id, relation FROM card_source_cards "
            "WHERE card_id = ? ORDER BY seq ASC",
            (card_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [{"card_id": r["source_card_id"], "relation": r["relation"]} for r in rows]

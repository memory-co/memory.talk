"""PositionStore -- answer candidate persistence: file canonical + SQLite.

A Position has **no global id** -- it is the card's subordinate, addressed
``<card_id>#p<n>`` (``p`` + a card-scoped sequence). The seq is minted on
insert from ``cards.position_count + 1`` (and bumps that counter).

File: cards/<bucket>/<card_id>/positions/<position>.json
(canonical immutable core: claim + created_at only; scope and forked_from
are mutable runtime state in SQLite, not part of the write-once file).
SQLite mirrors claim + created_at plus the up/down/neutral/review counters
+ scope + forked_from. credence is NOT stored -- computed by the service.
No FOREIGN KEY.
"""
from __future__ import annotations

import json

import aiosqlite

from memorytalk.provider.storage import Storage
from memorytalk.util.ids import position_seq


class PositionStore:
    PREFIX = "cards"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage):
        self.conn = conn
        self.storage = storage

    @staticmethod
    def _bucket(card_id: str) -> str:
        raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _doc_key(self, card_id: str, position: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/positions/{position}.json"

    # -- file layer --
    async def write_doc(self, card_id: str, position: dict) -> None:
        await self.storage.write_text(
            self._doc_key(card_id, position["position"]),
            json.dumps(position, ensure_ascii=False, indent=2),
        )

    async def read_doc(self, card_id: str, position: str) -> dict | None:
        text = await self.storage.read_text(self._doc_key(card_id, position))
        return json.loads(text) if text else None

    # -- positions table --
    async def insert(
        self, card_id: str, claim: str, created_at: str,
        *, scope: str = "", forked_from: str | None = None,
    ) -> str:
        """Mint the next card-scoped ``p<n>``, insert the row, bump
        ``cards.position_count``. Returns the assigned ``position`` ('p<n>')."""
        async with self.conn.execute(
            "SELECT position_count FROM cards WHERE card_id = ?", (card_id,),
        ) as cur:
            row = await cur.fetchone()
        count = row["position_count"] if row else 0
        position = position_seq(count + 1)
        await self.conn.execute(
            "INSERT INTO positions "
            "(card_id, position, claim, created_at, up_count, down_count, "
            " neutral_count, review_count, scope, forked_from) "
            "VALUES (?, ?, ?, ?, 0, 0, 0, 0, ?, ?)",
            (card_id, position, claim, created_at, scope, forked_from),
        )
        await self.conn.execute(
            "UPDATE cards SET position_count = position_count + 1 WHERE card_id = ?",
            (card_id,),
        )
        await self.conn.commit()
        return position

    async def get(self, card_id: str, position: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM positions WHERE card_id = ? AND position = ?",
            (card_id, position),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def exists(self, card_id: str, position: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM positions WHERE card_id = ? AND position = ?",
            (card_id, position),
        ) as cur:
            return await cur.fetchone() is not None

    async def list_for_card(self, card_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM positions WHERE card_id = ? ORDER BY created_at ASC, position ASC",
            (card_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def bump_argument(self, card_id: str, position: str, argument: int) -> None:
        """Increment the argument-specific bucket + review_count."""
        col = {1: "up_count", -1: "down_count", 0: "neutral_count"}.get(argument)
        if col is None:
            raise ValueError(f"argument must be -1/0/1, got {argument!r}")
        await self.conn.execute(
            f"UPDATE positions SET {col} = {col} + 1, review_count = review_count + 1 "
            f"WHERE card_id = ? AND position = ?",
            (card_id, position),
        )
        await self.conn.commit()

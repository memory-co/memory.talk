"""PositionStore -- answer candidate persistence: file canonical + SQLite.

File: cards/<bucket>/<card_id>/positions/<position_id>.json
(canonical immutable core: claim + created_at only; scope and
forked_from_position_id are mutable runtime state in SQLite, not part
of the write-once file). SQLite mirrors claim + created_at plus the
up/down/neutral/review counters + scope + forked_from_position_id.
credence is NOT stored -- computed by the service. No FOREIGN KEY.
"""
from __future__ import annotations

import json

import aiosqlite

from memorytalk.provider.storage import Storage


class PositionStore:
    PREFIX = "cards"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage):
        self.conn = conn
        self.storage = storage

    @staticmethod
    def _bucket(card_id: str) -> str:
        raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _doc_key(self, card_id: str, position_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/positions/{position_id}.json"

    # -- file layer --
    async def write_doc(self, card_id: str, position: dict) -> None:
        await self.storage.write_text(
            self._doc_key(card_id, position["position_id"]),
            json.dumps(position, ensure_ascii=False, indent=2),
        )

    async def read_doc(self, card_id: str, position_id: str) -> dict | None:
        text = await self.storage.read_text(self._doc_key(card_id, position_id))
        return json.loads(text) if text else None

    # -- positions table --
    async def insert(
        self, position_id: str, card_id: str, claim: str, created_at: str,
        *, scope: str = "", forked_from_position_id: str | None = None,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO positions "
            "(position_id, card_id, claim, created_at, up_count, down_count, "
            " neutral_count, review_count, scope, forked_from_position_id) "
            "VALUES (?, ?, ?, ?, 0, 0, 0, 0, ?, ?)",
            (position_id, card_id, claim, created_at, scope, forked_from_position_id),
        )
        await self.conn.commit()

    async def get(self, position_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM positions WHERE position_id = ?", (position_id,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def exists(self, position_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM positions WHERE position_id = ?", (position_id,),
        ) as cur:
            return await cur.fetchone() is not None

    async def list_for_card(self, card_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM positions WHERE card_id = ? ORDER BY created_at ASC",
            (card_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def bump_argument(self, position_id: str, argument: int) -> None:
        """Increment the argument-specific bucket + review_count."""
        col = {1: "up_count", -1: "down_count", 0: "neutral_count"}.get(argument)
        if col is None:
            raise ValueError(f"argument must be -1/0/1, got {argument!r}")
        await self.conn.execute(
            f"UPDATE positions SET {col} = {col} + 1, review_count = review_count + 1 "
            f"WHERE position_id = ?",
            (position_id,),
        )
        await self.conn.commit()

"""CardLinkStore -- card<->card IBIS edges (card_links), a governed object.

A row = subject ``card_id`` + card-scoped seq ``link`` ('l<n>') + ``type``
+ ``target_id`` + ``claim`` + up/down/neutral/review counters. The edge has
**no global id** -- it is the card's subordinate, addressed ``<card_id>#l<n>``.
The seq is minted on insert from ``cards.link_count + 1`` (and bumps it).

``target_type`` ('card' | 'position') is derived from the target_id (a
``#p`` fragment -> 'position', else 'card') and stored for filtering.
Idempotent on UNIQUE (card_id, type, target_id): a duplicate edge does not
mint a new seq -- the existing ``link`` is returned. No FOREIGN KEY.

File canonical: cards/<bucket>/<card_id>/links/<link>.json
(immutable core: type + target_id + claim + created_at). credence is NOT
stored -- computed by the service.
"""
from __future__ import annotations

import json

import aiosqlite

from memorytalk.provider.storage import Storage
from memorytalk.util.ids import FRAGMENT_SEP, POSITION_SEQ_PREFIX, link_seq


def _target_type(target_id: str) -> str:
    base, sep, seq = target_id.partition(FRAGMENT_SEP)
    if sep and seq.startswith(POSITION_SEQ_PREFIX):
        return "position"
    return "card"


class CardLinkStore:
    PREFIX = "cards"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage | None = None):
        self.conn = conn
        self.storage = storage

    @staticmethod
    def _bucket(card_id: str) -> str:
        raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _doc_key(self, card_id: str, link: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/links/{link}.json"

    # -- file layer --
    async def write_doc(self, card_id: str, link: dict) -> None:
        if self.storage is None:
            raise RuntimeError("CardLinkStore has no storage configured")
        await self.storage.write_text(
            self._doc_key(card_id, link["link"]),
            json.dumps(link, ensure_ascii=False, indent=2),
        )

    async def read_doc(self, card_id: str, link: str) -> dict | None:
        if self.storage is None:
            raise RuntimeError("CardLinkStore has no storage configured")
        text = await self.storage.read_text(self._doc_key(card_id, link))
        return json.loads(text) if text else None

    # -- card_links table --
    async def insert(
        self, card_id: str, type_: str, target_id: str, claim: str, created_at: str,
    ) -> str:
        """Mint the next card-scoped ``l<n>``, insert the edge, bump
        ``cards.link_count``. Idempotent on UNIQUE (card_id, type,
        target_id): a duplicate edge returns the existing ``link`` without
        minting. Returns the edge's ``link`` ('l<n>')."""
        existing = await self._find_link(card_id, type_, target_id)
        if existing is not None:
            return existing
        async with self.conn.execute(
            "SELECT link_count FROM cards WHERE card_id = ?", (card_id,),
        ) as cur:
            row = await cur.fetchone()
        count = row["link_count"] if row else 0
        link = link_seq(count + 1)
        await self.conn.execute(
            "INSERT INTO card_links "
            "(card_id, link, type, target_id, target_type, claim, "
            " up_count, down_count, neutral_count, review_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?)",
            (card_id, link, type_, target_id, _target_type(target_id), claim, created_at),
        )
        await self.conn.execute(
            "UPDATE cards SET link_count = link_count + 1 WHERE card_id = ?",
            (card_id,),
        )
        await self.conn.commit()
        return link

    async def _find_link(self, card_id: str, type_: str, target_id: str) -> str | None:
        async with self.conn.execute(
            "SELECT link FROM card_links "
            "WHERE card_id = ? AND type = ? AND target_id = ?",
            (card_id, type_, target_id),
        ) as cur:
            row = await cur.fetchone()
        return row["link"] if row else None

    async def get(self, card_id: str, link: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM card_links WHERE card_id = ? AND link = ?",
            (card_id, link),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def list_out(self, card_id: str) -> list[dict]:
        """Edges where this card is the subject."""
        async with self.conn.execute(
            "SELECT * FROM card_links WHERE card_id = ? ORDER BY created_at ASC, link ASC",
            (card_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_in(self, target_id: str) -> list[dict]:
        """Edges pointing at this id (reverse lookup, idx_v4_links_target)."""
        async with self.conn.execute(
            "SELECT * FROM card_links WHERE target_id = ? ORDER BY created_at ASC",
            (target_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def bump_argument(self, card_id: str, link: str, argument: int) -> None:
        """Increment the argument-specific bucket + review_count on a link."""
        col = {1: "up_count", -1: "down_count", 0: "neutral_count"}.get(argument)
        if col is None:
            raise ValueError(f"argument must be -1/0/1, got {argument!r}")
        await self.conn.execute(
            f"UPDATE card_links SET {col} = {col} + 1, review_count = review_count + 1 "
            f"WHERE card_id = ? AND link = ?",
            (card_id, link),
        )
        await self.conn.commit()

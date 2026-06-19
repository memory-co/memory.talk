"""V4ReadService — read a v4 card or position by id.

Read-only; no engagement side effects (v4 stores no read_count). credence
is computed here and injected; Positions on a card come back sorted by the
"current answer" order (credence DESC, tie → most-recent review). The API
dispatches ``sess_`` ids to the v3 read service — this service owns only
``card_`` and ``pos_``.
"""
from __future__ import annotations

from memorytalk.repository import SQLiteStore
from memorytalk.service.v4_credence import sort_key, with_credence


class V4ReadService:
    def __init__(self, db: SQLiteStore):
        self.db = db

    async def _last_reviewed_at(self, position_id: str) -> str | None:
        reviews = await self.db.reviews.list_for_position(position_id)  # DESC
        return reviews[0]["created_at"] if reviews else None

    async def _injected_positions(self, card_id: str) -> list[dict]:
        rows = await self.db.positions.list_for_card(card_id)
        injected = [
            with_credence(r, await self._last_reviewed_at(r["position_id"]))
            for r in rows
        ]
        injected.sort(key=sort_key, reverse=True)   # current answer first
        return injected

    async def read_card(self, card_id: str) -> dict | None:
        card = await self.db.cards.get(card_id)
        if card is None:
            return None
        positions = await self._injected_positions(card_id)
        links = [
            {**e, "dir": "out"} for e in await self.db.card_links.list_out(card_id)
        ] + [
            {**e, "dir": "in"} for e in await self.db.card_links.list_in(card_id)
        ]
        sessions = await self.db.card_sessions.list_for_card(card_id)
        return {
            **card,
            "positions": positions,
            "links": links,
            "sessions": sessions,
        }

    async def read_position(self, position_id: str) -> dict | None:
        row = await self.db.positions.get(position_id)
        if row is None:
            return None
        injected = with_credence(row, await self._last_reviewed_at(position_id))
        reviews = await self.db.reviews.list_for_position(position_id)   # DESC
        return {**injected, "reviews": reviews}

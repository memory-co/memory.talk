"""V4ReadService — read a v4 card or position by id.

Read-only; no engagement side effects (v4 stores no read_count). credence
is computed here and injected; Positions on a card come back sorted by the
"current answer" order (credence DESC, tie → most-recent review). Links are
surfaced with their ``link`` seq, ``claim`` and credence (a CardLink is a
governed object). The API dispatches ``sess_`` ids to the v3 read service —
this service owns ``card_`` and the ``card_id#p<n>`` / ``card_id#l<n>``
fragments.
"""
from __future__ import annotations

from memorytalk.service.credence import credence, sort_key, with_credence
from memorytalk.repository import SQLiteStore
from memorytalk.util.ids import FRAGMENT_SEP


def _address(card_id: str, seq: str) -> str:
    return f"{card_id}{FRAGMENT_SEP}{seq}"


class V4ReadService:
    def __init__(self, db: SQLiteStore):
        self.db = db

    async def _last_reviewed_at(self, card_id: str, position: str) -> str | None:
        reviews = await self.db.reviews.list_for_target(card_id, position)  # DESC
        return reviews[0]["created_at"] if reviews else None

    @staticmethod
    def _addr_position(card_id: str, injected: dict) -> dict:
        """Add the addressed id ``card_id#p<n>`` to an injected position."""
        return {**injected, "id": _address(card_id, injected["position"])}

    async def _injected_positions(self, card_id: str) -> list[dict]:
        rows = await self.db.positions.list_for_card(card_id)
        injected = [
            self._addr_position(
                card_id,
                with_credence(r, await self._last_reviewed_at(card_id, r["position"])),
            )
            for r in rows
        ]
        injected.sort(key=sort_key, reverse=True)   # current answer first
        return injected

    @staticmethod
    def _link_view(card_id: str, e: dict, direction: str) -> dict:
        return {
            **e, "dir": direction, "id": _address(card_id, e["link"]),
            "credence": credence(e["up_count"], e["down_count"]),
        }

    async def read_card(self, card_id: str) -> dict | None:
        card = await self.db.cards.get(card_id)
        if card is None:
            return None
        positions = await self._injected_positions(card_id)
        links = [
            self._link_view(card_id, e, "out")
            for e in await self.db.card_links.list_out(card_id)
        ] + [
            self._link_view(e["card_id"], e, "in")
            for e in await self.db.card_links.list_in(card_id)
        ]
        sessions = await self.db.card_sessions.list_for_card(card_id)
        return {
            **card,
            "positions": positions,
            "links": links,
            "sessions": sessions,
        }

    async def read_position(self, card_id: str, position: str) -> dict | None:
        row = await self.db.positions.get(card_id, position)
        if row is None:
            return None
        injected = self._addr_position(
            card_id, with_credence(row, await self._last_reviewed_at(card_id, position)),
        )
        reviews = await self.db.reviews.list_for_target(card_id, position)   # DESC
        return {**injected, "reviews": reviews}

    async def read_link(self, card_id: str, link: str) -> dict | None:
        row = await self.db.card_links.get(card_id, link)
        if row is None:
            return None
        reviews = await self.db.reviews.list_for_target(card_id, link)   # DESC
        return {
            **row, "id": _address(card_id, link),
            "credence": credence(row["up_count"], row["down_count"]),
            "reviews": reviews,
        }

"""V4SearchService — deliberate retrieval over the v4 question graph.

Hybrid issue+claim relevance (no sinking/forum dynamics — v4 has none).
Each returned card carries its **current answer** (``top_position``): the
claim-hit Position if the query matched one, else the highest-credence
Position. An optional ``where`` DSL filters on the current answer's tallies
(``up_count`` / ``down_count`` / ``neutral_count`` / ``credence``) and card
metadata (``position_count`` / ``created_at``). Empty query → newest first.
"""
from __future__ import annotations

from memorytalk.repository import SQLiteStore
from memorytalk.searchbase import SearchBackend
from memorytalk.service.cards import CardServiceError
from memorytalk.service.credence import sort_key, with_credence
from memorytalk.service.card_retrieval import retrieve
from memorytalk.util import dsl as dsl_mod

_MAX_LIMIT = 200


class V4SearchService:
    def __init__(self, db: SQLiteStore, search: SearchBackend | None):
        self.db = db
        self.searchbase = search

    async def _injected_positions(self, card_id: str) -> list[dict]:
        rows = await self.db.positions.list_for_card(card_id)
        out = []
        for r in rows:
            reviews = await self.db.reviews.list_for_position(r["position_id"])
            out.append(with_credence(r, reviews[0]["created_at"] if reviews else None))
        out.sort(key=sort_key, reverse=True)
        return out

    def _top_position(self, positions: list[dict], matched_id: str | None) -> dict | None:
        if not positions:
            return None
        if matched_id:
            for p in positions:
                if p["position_id"] == matched_id:
                    return p
        return positions[0]   # highest credence (already sorted)

    async def _card_view(self, card_id: str, relevance: float | None, matched_id: str | None) -> dict | None:
        card = await self.db.cards.get(card_id)
        if card is None:
            return None
        positions = await self._injected_positions(card_id)
        top = self._top_position(positions, matched_id)
        return {
            "card_id": card_id, "issue": card["issue"],
            "created_at": card["created_at"],
            "position_count": card["position_count"],
            "top_position": top,
            "relevance": relevance,
        }

    @staticmethod
    def _dsl_candidate(view: dict) -> dict:
        """Flatten current-answer tallies + card metadata for the DSL."""
        top = view["top_position"] or {}
        return {
            "up_count": top.get("up_count", 0),
            "down_count": top.get("down_count", 0),
            "neutral_count": top.get("neutral_count", 0),
            "review_count": top.get("review_count", 0),
            "credence": top.get("credence", 0),
            "position_count": view["position_count"],
            "created_at": view["created_at"],
        }

    async def search(self, query: str, where: str | None, limit: int = 20) -> dict:
        if not isinstance(query, str):
            raise CardServiceError("query required")
        if not 1 <= limit <= _MAX_LIMIT:
            raise CardServiceError(f"limit out of range [1, {_MAX_LIMIT}]")
        try:
            flt = dsl_mod.parse(where or "")
        except dsl_mod.DSLError as e:
            raise CardServiceError(str(e)) from e

        # ── candidate gather ──
        if query.strip() and self.searchbase is not None:
            ranked = await retrieve(self.searchbase, query, limit)
            cand = [(cid, m["relevance"], m["position_id"]) for cid, m in ranked]
        else:
            # empty query (or no searchbase) → newest-first listing, DSL only
            _, rows = await self.db.cards.list_cards(limit=max(limit * 5, 100))
            cand = [(r["card_id"], None, None) for r in rows]

        # ── build views + DSL filter ──
        views: list[dict] = []
        for cid, relevance, matched in cand:
            view = await self._card_view(cid, relevance, matched)
            if view is None:
                continue
            if not flt.empty() and not flt.evaluate(self._dsl_candidate(view), "card"):
                continue
            views.append(view)

        # ── order ──
        if query.strip() and self.searchbase is not None:
            views.sort(key=lambda v: (v["relevance"] or 0.0), reverse=True)
        else:
            views.sort(key=lambda v: v["created_at"], reverse=True)

        total = len(views)
        return {"query": query, "total": total, "returned": min(total, limit),
                "cards": views[:limit]}

"""V4SearchService — unified deliberate retrieval across three memories.

``POST /v4/search`` is the agent's conscious "go look it up" surface. It
spans the three things memory.talk stores and ranks them in a single
relevance-ordered stream:

  - **card**     — the v4 question graph. Collide the query on ``issue``
                   AND ``claim`` (``cards`` + ``positions`` collections);
                   each hit lands its card carrying the **current answer**
                   (claim-hit Position, else highest-credence Position).
  - **insight**  — the migrated v3 knowledge (``insights`` collection).
  - **session**  — raw conversation rounds (``rounds`` collection); a hit
                   is a round excerpt with its session context.

Why unified: real installs have many sessions + insights but **zero v4
cards** until the mark write-path builds the graph. A card-only search is
useless on day one; folding in insights + sessions means ``search`` works
from the first ingest (issue #7).

The common ranking axis across all three is the raw retrieval relevance
(searchbase ``score``). There is no v3-style sinking/forum formula — v4
relevance is computed only at query time.

The optional ``where`` DSL filters the **card** results' current-answer
tallies (``up_count`` / ``down_count`` / ``neutral_count`` / ``credence``)
and card metadata (``position_count`` / ``created_at``). It does NOT apply
to insight / session results — those are returned by relevance only. If a
``where`` is given and no cards match, insight / session hits still come
back.

Empty query → newest-first card listing (DSL only), no insight/session
collection (there is nothing to rank them by).
"""
from __future__ import annotations

from memorytalk.repository import SQLiteStore
from memorytalk.searchbase import Query, SearchBackend
from memorytalk.service.cards import CardServiceError
from memorytalk.service.credence import sort_key, with_credence
from memorytalk.service.card_retrieval import retrieve
from memorytalk.service.searchbase_schema import INSIGHTS, ROUNDS
from memorytalk.util import dsl as dsl_mod

_MAX_LIMIT = 200
# Oversample the insight / round buckets so the cross-bucket merge has
# room to interleave (a card hit may outrank many weak round echoes).
_INSIGHT_OVERSAMPLE = 3
_ROUNDS_OVERSAMPLE = 5
# Per-session round excerpt cap — sessions can be huge; one round's text
# is bounded so a single long turn doesn't dominate the response.
_ROUND_EXCERPT_CHARS = 400
# How many hit rounds to surface per session result.
_HITS_PER_SESSION = 3


def _session_relevance(scores: list[float]) -> float:
    """A session's relevance is its single strongest hit (see the long
    rationale in ``service/search.py::_aggregate_session_relevance`` —
    ``max`` beats noisy-OR on the RRF scale)."""
    return max(scores) if scores else 0.0


class V4SearchService:
    def __init__(self, db: SQLiteStore, search: SearchBackend | None):
        self.db = db
        self.searchbase = search

    # ──────── card bucket ────────

    async def _injected_positions(self, card_id: str) -> list[dict]:
        rows = await self.db.positions.list_for_card(card_id)
        out = []
        for r in rows:
            reviews = await self.db.reviews.list_for_target(card_id, r["position"])
            inj = with_credence(r, reviews[0]["created_at"] if reviews else None)
            inj["id"] = f"{card_id}#{r['position']}"
            out.append(inj)
        out.sort(key=sort_key, reverse=True)
        return out

    def _top_position(self, positions: list[dict], matched_id: str | None) -> dict | None:
        if not positions:
            return None
        if matched_id:
            for p in positions:
                if p["id"] == matched_id:
                    return p
        return positions[0]   # highest credence (already sorted)

    async def _card_view(self, card_id: str, relevance: float | None, matched_id: str | None) -> dict | None:
        card = await self.db.cards.get(card_id)
        if card is None:
            return None
        positions = await self._injected_positions(card_id)
        top = self._top_position(positions, matched_id)
        return {
            "kind": "card",
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

    async def _collect_cards(self, query: str, limit: int, flt) -> list[dict]:
        # ── candidate gather ──
        if query.strip() and self.searchbase is not None:
            ranked = await retrieve(self.searchbase, query, limit)
            cand = [(cid, m["relevance"], m["position_addr"]) for cid, m in ranked]
        else:
            # empty query (or no searchbase) → newest-first listing, DSL only
            _, rows = await self.db.cards.list_cards(limit=max(limit * 5, 100))
            cand = [(r["card_id"], None, None) for r in rows]

        views: list[dict] = []
        for cid, relevance, matched in cand:
            view = await self._card_view(cid, relevance, matched)
            if view is None:
                continue
            if not flt.empty() and not flt.evaluate(self._dsl_candidate(view), "card"):
                continue
            views.append(view)
        return views

    # ──────── insight bucket ────────

    async def _collect_insights(self, query: str, limit: int) -> list[dict]:
        if self.searchbase is None:
            return []
        hits = await self.searchbase.search(
            INSIGHTS, Query(text=query, top_k=limit * _INSIGHT_OVERSAMPLE),
        )
        out: list[dict] = []
        for hit in hits:
            iid = hit.id
            if not iid:
                continue
            row = await self.db.insights.get(iid)
            if row is None:
                continue
            out.append({
                "kind": "insight",
                "insight_id": iid,
                "insight": row["insight"],
                "created_at": row["created_at"],
                "relevance": float(hit.score),
            })
        return out

    # ──────── session bucket ────────

    async def _collect_sessions(self, query: str, limit: int) -> list[dict]:
        if self.searchbase is None:
            return []
        hits = await self.searchbase.search(
            ROUNDS, Query(text=query, top_k=limit * _ROUNDS_OVERSAMPLE),
        )
        by_session: dict[str, list[dict]] = {}
        for hit in hits:
            sid = hit.fields.get("session_id")
            if not sid:
                continue
            by_session.setdefault(sid, []).append({
                "index": int(hit.fields["idx"]),
                "role": hit.fields.get("role") or "",
                "score": float(hit.score),
            })

        out: list[dict] = []
        for sid, hit_list in by_session.items():
            srow = await self.db.sessions.get(sid)
            if srow is None:
                continue
            hit_list.sort(key=lambda h: h["score"], reverse=True)
            relevance = _session_relevance([h["score"] for h in hit_list])
            rounds = await self.db.sessions.read_rounds_file(srow["source"], sid)
            by_idx = {r["idx"]: r for r in rounds}
            hits_shown: list[dict] = []
            for h in hit_list[:_HITS_PER_SESSION]:
                cur = by_idx.get(h["index"])
                text = (cur.get("text") if cur else None) or ""
                hits_shown.append({
                    "index": h["index"],
                    "role": (cur.get("role") if cur else None) or h["role"],
                    "text": text[:_ROUND_EXCERPT_CHARS],
                    "score": h["score"],
                })
            out.append({
                "kind": "session",
                "session_id": sid,
                "source": srow["source"],
                "round_count": srow["round_count"],
                "created_at": srow["created_at"],
                "relevance": relevance,
                "hit_count": len(hit_list),
                "hits": hits_shown,
            })
        return out

    # ──────── orchestration ────────

    async def search(self, query: str, where: str | None, limit: int = 20) -> dict:
        if not isinstance(query, str):
            raise CardServiceError("query required")
        if not 1 <= limit <= _MAX_LIMIT:
            raise CardServiceError(f"limit out of range [1, {_MAX_LIMIT}]")
        try:
            flt = dsl_mod.parse(where or "")
        except dsl_mod.DSLError as e:
            raise CardServiceError(str(e)) from e

        has_query = bool(query.strip()) and self.searchbase is not None

        cards = await self._collect_cards(query, limit, flt)
        # Insight / session buckets are relevance-only — skip them when
        # there's no query to rank against (empty-query is a card listing).
        insights: list[dict] = []
        sessions: list[dict] = []
        if has_query:
            insights = await self._collect_insights(query, limit)
            sessions = await self._collect_sessions(query, limit)

        # ── merge + rank ──
        results = cards + insights + sessions
        if has_query:
            # Raw retrieval relevance is the shared axis across all three.
            results.sort(key=lambda v: (v.get("relevance") or 0.0), reverse=True)
        else:
            # Empty query → newest-first (cards only).
            results.sort(key=lambda v: v["created_at"], reverse=True)

        total = len(results)
        results = results[:limit]
        return {
            "query": query,
            "total": total,
            "returned": len(results),
            # ``cards`` kept as the response key for back-compat; the list is
            # now a mixed stream tagged by each item's ``kind`` field.
            "cards": results,
        }

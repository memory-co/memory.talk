"""v4 hybrid retrieval — collide on issue AND claim.

A prompt/query is embedded once and run against both v4 collections:
``cards`` (issue) and ``positions`` (claim). A card hit lands the card
directly; a position hit lands its owning card (via the stored ``card_id``
field) AND remembers which Position matched — that's the answer-side signal
that makes "the side of the debate closest to the current context floats
up" work without any explicit contention logic.

Returns cards ranked by relevance (= best of its card-hit / position-hit
similarity), each annotated with the best-matching position id (or None).
"""
from __future__ import annotations

from memorytalk.searchbase import Query, SearchBackend
from memorytalk.service.searchbase_schema import V4_CARDS, V4_POSITIONS

_OVERSAMPLE = 4


async def retrieve(
    search: SearchBackend, query: str, top_k: int,
) -> list[tuple[str, dict]]:
    """Return ``[(card_id, {"relevance": float, "position_id": str|None})]``
    ranked by relevance DESC. ``position_id`` is the best-matching Position
    for that card (a claim hit), or None when only the issue matched."""
    n = max(top_k * _OVERSAMPLE, top_k + 5)
    card_hits = await search.search(V4_CARDS, Query(text=query, top_k=n))
    pos_hits = await search.search(V4_POSITIONS, Query(text=query, top_k=n))

    agg: dict[str, dict] = {}
    for h in card_hits:
        if not h.id:
            continue
        cur = agg.setdefault(h.id, {"relevance": 0.0, "position_id": None, "_pos": -1.0})
        cur["relevance"] = max(cur["relevance"], h.score)
    for h in pos_hits:
        cid = h.fields.get("card_id")
        if not cid:
            continue
        cur = agg.setdefault(cid, {"relevance": 0.0, "position_id": None, "_pos": -1.0})
        cur["relevance"] = max(cur["relevance"], h.score)
        if h.score > cur["_pos"]:
            cur["_pos"] = h.score
            cur["position_id"] = h.id

    ranked = sorted(agg.items(), key=lambda kv: kv[1]["relevance"], reverse=True)
    return [(cid, {"relevance": v["relevance"], "position_id": v["position_id"]})
            for cid, v in ranked]

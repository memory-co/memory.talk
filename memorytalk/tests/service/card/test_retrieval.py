"""card_retrieval.retrieve — collides on BOTH issue (cards) and claim
(positions) vector collections (design: recall 撞 issue + claim).

A fake backend returns hits per collection so we can assert: a claim-only
hit lands its owning card (via the position's ``card_id`` field) AND
remembers the matched position address; relevance is the best of the two
signals.
"""
from __future__ import annotations

from memorytalk.searchbase import Hit, Query
from memorytalk.service.card_retrieval import retrieve
from memorytalk.service.searchbase_schema import V4_CARDS, V4_POSITIONS


class _FakeBackend:
    """Returns canned hits per collection; records which collections were hit."""

    def __init__(self, *, card_hits, pos_hits):
        self._card_hits = card_hits
        self._pos_hits = pos_hits
        self.searched: list[str] = []

    async def search(self, collection: str, query: Query):
        self.searched.append(collection)
        return self._card_hits if collection == V4_CARDS else self._pos_hits


async def test_retrieve_queries_both_collections():
    be = _FakeBackend(card_hits=[], pos_hits=[])
    await retrieve(be, "anything", top_k=5)
    assert V4_CARDS in be.searched and V4_POSITIONS in be.searched


async def test_claim_only_hit_lands_owning_card():
    # No card(issue) hit; only a position(claim) hit → its owning card is
    # surfaced with the matched position address (the answer-side signal).
    be = _FakeBackend(
        card_hits=[],
        pos_hits=[Hit(id="card_x#p2", score=0.81, fields={"card_id": "card_x"})],
    )
    ranked = await retrieve(be, "q", top_k=5)
    assert len(ranked) == 1
    cid, meta = ranked[0]
    assert cid == "card_x"
    assert meta["relevance"] == 0.81
    assert meta["position_addr"] == "card_x#p2"


async def test_relevance_is_best_of_issue_and_claim():
    # Same card hit on both sides → relevance = max of the two scores.
    be = _FakeBackend(
        card_hits=[Hit(id="card_x", score=0.40)],
        pos_hits=[Hit(id="card_x#p1", score=0.90, fields={"card_id": "card_x"})],
    )
    ranked = await retrieve(be, "q", top_k=5)
    cid, meta = ranked[0]
    assert cid == "card_x" and meta["relevance"] == 0.90
    assert meta["position_addr"] == "card_x#p1"

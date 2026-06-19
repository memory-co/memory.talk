"""V4ReadService + V4SearchService (empty-query / DSL path, no backend)."""
from __future__ import annotations

import pytest

from memorytalk.schemas.v4.requests import (
    CreateCardRequest, CreatePositionRequest, CreateReviewRequest,
)


async def _card_with_positions(cardsvc):
    """Card with two positions; p_hi gets +2 (credence 2), p_lo gets -1."""
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="Which db?"))
    p_lo = await cardsvc.svc.add_position(cid, CreatePositionRequest(claim="MySQL"))
    p_hi = await cardsvc.svc.add_position(cid, CreatePositionRequest(claim="SQLite", scope="single-node"))
    for ix in ("1", "2"):
        await cardsvc.svc.review(p_hi, CreateReviewRequest(
            position_id=p_hi, session_id=cardsvc.session, indexes=ix, argument=1))
    await cardsvc.svc.review(p_lo, CreateReviewRequest(
        position_id=p_lo, session_id=cardsvc.session, indexes="3", argument=-1))
    return cid, p_hi, p_lo


async def test_read_card_sorts_current_answer_first(cardsvc):
    cid, p_hi, p_lo = await _card_with_positions(cardsvc)
    card = await cardsvc.read.read_card(cid)
    assert card["issue"] == "Which db?"
    assert [p["position_id"] for p in card["positions"]][0] == p_hi   # credence 2 first
    assert card["positions"][0]["credence"] == 2
    assert card["positions"][0]["scope"] == "single-node"
    assert card["positions"][-1]["position_id"] == p_lo               # credence -1 last


async def test_read_card_missing_returns_none(cardsvc):
    assert await cardsvc.read.read_card("card_nope") is None


async def test_read_position_attaches_reviews(cardsvc):
    cid, p_hi, _ = await _card_with_positions(cardsvc)
    pos = await cardsvc.read.read_position(p_hi)
    assert pos["credence"] == 2 and pos["up_count"] == 2
    assert len(pos["reviews"]) == 2   # DESC by created_at


async def test_read_card_includes_links_both_directions(cardsvc):
    from memorytalk.schemas.v4.requests import CreateLinkRequest
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa", card_id="card_a00001"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="qb", card_id="card_b00002"))
    await cardsvc.svc.link(a, CreateLinkRequest(card_id=a, type="specializes", target_id=b))
    card_a = await cardsvc.read.read_card(a)
    card_b = await cardsvc.read.read_card(b)
    assert any(l["dir"] == "out" and l["target_id"] == b for l in card_a["links"])
    assert any(l["dir"] == "in" and l["card_id"] == a for l in card_b["links"])


async def test_search_empty_query_lists_newest_first(cardsvc):
    c1 = await cardsvc.svc.create_card(CreateCardRequest(issue="first"))
    c2 = await cardsvc.svc.create_card(CreateCardRequest(issue="second"))
    res = await cardsvc.search.search("", None, limit=20)
    ids = [c["card_id"] for c in res["cards"]]
    assert ids[0] == c2 and c1 in ids   # newest first
    assert res["total"] == 2


async def test_search_where_dsl_filters_on_credence(cardsvc):
    cid, p_hi, _ = await _card_with_positions(cardsvc)
    empty = await cardsvc.svc.create_card(CreateCardRequest(issue="no answers"))
    # credence > 1 → only the card whose top answer has credence 2
    res = await cardsvc.search.search("", "credence > 1", limit=20)
    ids = [c["card_id"] for c in res["cards"]]
    assert cid in ids and empty not in ids
    # top_position reflects the current answer
    hit = next(c for c in res["cards"] if c["card_id"] == cid)
    assert hit["top_position"]["position_id"] == p_hi


async def test_search_bad_limit_rejected(cardsvc):
    from memorytalk.service.cards import CardServiceError
    with pytest.raises(CardServiceError):
        await cardsvc.search.search("", None, limit=999)

"""CardService write path — create / position / review / link / session."""
from __future__ import annotations

import pytest

from memorytalk.schemas.v4.requests import (
    CreateCardRequest, CreateLinkRequest, CreatePositionRequest,
    CreateReviewRequest, SourceRef,
)
from memorytalk.service.cards import CardConflict, CardNotFound, CardServiceError


async def test_create_card_mints_id_and_persists(cardsvc):
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="Which db?"))
    assert cid.startswith("card_")
    row = await cardsvc.db.v4cards.get(cid)
    assert row["issue"] == "Which db?" and row["position_count"] == 0
    assert (await cardsvc.db.v4cards.read_doc(cid))["issue"] == "Which db?"


async def test_create_card_rejects_empty_issue(cardsvc):
    with pytest.raises(CardServiceError):
        await cardsvc.svc.create_card(CreateCardRequest(issue="  "))


async def test_create_card_conflict_on_dup_id(cardsvc):
    await cardsvc.svc.create_card(CreateCardRequest(issue="q", card_id="card_dup01"))
    with pytest.raises(CardConflict):
        await cardsvc.svc.create_card(CreateCardRequest(issue="q2", card_id="card_dup01"))


async def test_add_position_bumps_count_and_links_source(cardsvc):
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="Which db?"))
    pid = await cardsvc.svc.add_position(cid, CreatePositionRequest(
        claim="SQLite", scope="single-node only",
        source=SourceRef(session_id=cardsvc.session, indexes="1-3"),
    ))
    assert pid.startswith("pos_")
    assert (await cardsvc.db.v4cards.get(cid))["position_count"] == 1
    prow = await cardsvc.db.positions.get(pid)
    assert prow["claim"] == "SQLite" and prow["scope"] == "single-node only"
    sessions = await cardsvc.db.card_sessions.list_for_card(cid)
    assert sessions[0]["session_id"] == cardsvc.session
    assert sessions[0]["position_id"] == pid


async def test_add_position_unknown_card_404(cardsvc):
    with pytest.raises(CardNotFound):
        await cardsvc.svc.add_position("card_nope", CreatePositionRequest(claim="x"))


async def test_add_position_fork_lineage(cardsvc):
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="q"))
    p1 = await cardsvc.svc.add_position(cid, CreatePositionRequest(claim="a"))
    p2 = await cardsvc.svc.add_position(cid, CreatePositionRequest(
        claim="a refined", forked_from_position_id=p1))
    assert (await cardsvc.db.positions.get(p2))["forked_from_position_id"] == p1


async def test_review_bumps_argument_tallies(cardsvc):
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="q"))
    pid = await cardsvc.svc.add_position(cid, CreatePositionRequest(claim="a"))
    await cardsvc.svc.review(pid, CreateReviewRequest(
        position_id=pid, session_id=cardsvc.session, indexes="2", argument=1))
    await cardsvc.svc.review(pid, CreateReviewRequest(
        position_id=pid, session_id=cardsvc.session, indexes="3", argument=-1))
    row = await cardsvc.db.positions.get(pid)
    assert row["up_count"] == 1 and row["down_count"] == 1 and row["review_count"] == 2


async def test_review_unknown_position_404(cardsvc):
    with pytest.raises(CardNotFound):
        await cardsvc.svc.review("pos_nope", CreateReviewRequest(
            position_id="pos_nope", session_id=cardsvc.session, indexes="1", argument=1))


async def test_link_idempotent_and_bumps_once(cardsvc):
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="qb"))
    await cardsvc.svc.link(a, CreateLinkRequest(card_id=a, type="specializes", target_id=b))
    await cardsvc.svc.link(a, CreateLinkRequest(card_id=a, type="specializes", target_id=b))
    assert (await cardsvc.db.v4cards.get(a))["link_count"] == 1   # bumped once
    out = await cardsvc.db.card_links.list_out(a)
    assert len(out) == 1 and out[0]["target_type"] == "card"


async def test_link_related_canonicalized(cardsvc):
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa", card_id="card_aaa"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="qb", card_id="card_bbb"))
    # link from the larger id; stored under the smaller (canonical) subject
    r1 = await cardsvc.svc.link(b, CreateLinkRequest(card_id=b, type="related", target_id=a))
    assert r1["card_id"] == "card_aaa" and r1["target_id"] == "card_bbb"
    # reverse direction dedupes to the same canonical row
    r2 = await cardsvc.svc.link(a, CreateLinkRequest(card_id=a, type="related", target_id=b))
    assert len(await cardsvc.db.card_links.list_out("card_aaa")) == 1


async def test_link_position_target_only_suggested_by(cardsvc):
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa"))
    with pytest.raises(CardServiceError):
        await cardsvc.svc.link(a, CreateLinkRequest(
            card_id=a, type="specializes", target_id="pos_xyz"))
    # suggested_by → position target is allowed (dangling tolerated)
    r = await cardsvc.svc.link(a, CreateLinkRequest(
        card_id=a, type="suggested_by", target_id="pos_xyz"))
    assert r["target_type"] == "position"

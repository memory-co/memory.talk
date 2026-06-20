"""CardService write path — create / position / review / link / session."""
from __future__ import annotations

import pytest

from memorytalk.schemas.card_requests import (
    CreateCardRequest, CreateLinkRequest, CreatePositionRequest,
    CreateReviewRequest, SourceRef,
)
from memorytalk.service.cards import CardConflict, CardNotFound, CardServiceError


async def test_create_card_mints_id_and_persists(cardsvc):
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="Which db?"))
    assert cid.startswith("card_")
    row = await cardsvc.db.cards.get(cid)
    assert row["issue"] == "Which db?" and row["position_count"] == 0
    assert (await cardsvc.db.cards.read_doc(cid))["issue"] == "Which db?"


async def test_create_card_rejects_empty_issue(cardsvc):
    with pytest.raises(CardServiceError):
        await cardsvc.svc.create_card(CreateCardRequest(issue="  "))


async def test_create_card_conflict_on_dup_id(cardsvc):
    await cardsvc.svc.create_card(CreateCardRequest(issue="q", card_id="card_dup01"))
    with pytest.raises(CardConflict):
        await cardsvc.svc.create_card(CreateCardRequest(issue="q2", card_id="card_dup01"))


async def test_add_position_bumps_count_and_links_source(cardsvc):
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="Which db?"))
    pos = await cardsvc.svc.add_position(cid, CreatePositionRequest(
        claim="SQLite", scope="single-node only",
        source=SourceRef(session_id=cardsvc.session, indexes="1-3"),
    ))
    assert pos == "p1"
    assert (await cardsvc.db.cards.get(cid))["position_count"] == 1
    prow = await cardsvc.db.positions.get(cid, pos)
    assert prow["claim"] == "SQLite" and prow["scope"] == "single-node only"
    # provenance lands in position_sessions (not card_sessions, which is the
    # mark write-path, deferred)
    ps = await cardsvc.db.position_sessions.list_for_position(cid, pos)
    assert ps[0]["session_id"] == cardsvc.session and ps[0]["position"] == pos
    # file doc carries the position seq
    assert (await cardsvc.db.positions.read_doc(cid, pos))["position"] == pos


async def test_add_position_multi_source_writes_one_row_each(cardsvc):
    # Every --source must land its own position_sessions row under the minted
    # p<n> (the old behaviour POSTed overflow sources to a card-level bucket).
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="Which db?"))
    pos = await cardsvc.svc.add_position(cid, CreatePositionRequest(
        claim="SQLite",
        sources=[
            SourceRef(session_id=cardsvc.session, indexes="1-3"),
            SourceRef(session_id=cardsvc.session2, indexes="4,5"),
        ],
    ))
    ps = await cardsvc.db.position_sessions.list_for_position(cid, pos)
    assert len(ps) == 2
    # all rows carry the minted position seq (never the '' card-level bucket)
    assert all(r["position"] == pos for r in ps)
    assert {r["session_id"] for r in ps} == {cardsvc.session, cardsvc.session2}
    assert {r["indexes"] for r in ps} == {"1-3", "4,5"}


async def test_add_position_source_and_sources_union(cardsvc):
    # ``source`` (single) + ``sources`` (list) union, all under p<n>.
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="Which db?"))
    pos = await cardsvc.svc.add_position(cid, CreatePositionRequest(
        claim="SQLite",
        source=SourceRef(session_id=cardsvc.session, indexes="1"),
        sources=[SourceRef(session_id=cardsvc.session2, indexes="2")],
    ))
    ps = await cardsvc.db.position_sessions.list_for_position(cid, pos)
    assert {r["session_id"] for r in ps} == {cardsvc.session, cardsvc.session2}
    assert all(r["position"] == pos for r in ps)


async def test_add_position_unknown_card_404(cardsvc):
    with pytest.raises(CardNotFound):
        await cardsvc.svc.add_position("card_nope", CreatePositionRequest(claim="x"))


async def test_add_position_fork_lineage(cardsvc):
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="q"))
    p1 = await cardsvc.svc.add_position(cid, CreatePositionRequest(claim="a"))
    p2 = await cardsvc.svc.add_position(cid, CreatePositionRequest(
        claim="a refined", forked_from=p1))
    assert (await cardsvc.db.positions.get(cid, p2))["forked_from"] == p1


async def test_review_bumps_argument_tallies(cardsvc):
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="q"))
    pos = await cardsvc.svc.add_position(cid, CreatePositionRequest(claim="a"))
    target = f"{cid}#{pos}"
    await cardsvc.svc.review(target, CreateReviewRequest(
        target=target, session_id=cardsvc.session, indexes="2", argument=1))
    await cardsvc.svc.review(target, CreateReviewRequest(
        target=target, session_id=cardsvc.session, indexes="3", argument=-1))
    row = await cardsvc.db.positions.get(cid, pos)
    assert row["up_count"] == 1 and row["down_count"] == 1 and row["review_count"] == 2


async def test_review_on_link_bumps_link_tallies(cardsvc):
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="qb"))
    res = await cardsvc.svc.link(a, CreateLinkRequest(
        type="specializes", target_id=b, claim="b narrows a"))
    target = f"{a}#{res['link']}"
    out = await cardsvc.svc.review(target, CreateReviewRequest(
        target=target, session_id=cardsvc.session, indexes="1", argument=1))
    assert out["target_kind"] == "link"
    row = await cardsvc.db.card_links.get(a, res["link"])
    assert row["up_count"] == 1 and row["review_count"] == 1


async def test_review_unknown_position_404(cardsvc):
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="q"))
    target = f"{cid}#p9"
    with pytest.raises(CardNotFound):
        await cardsvc.svc.review(target, CreateReviewRequest(
            target=target, session_id=cardsvc.session, indexes="1", argument=1))


async def test_review_bad_target_rejected(cardsvc):
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="q"))
    with pytest.raises(CardServiceError):
        await cardsvc.svc.review(cid, CreateReviewRequest(
            target=cid, session_id=cardsvc.session, indexes="1", argument=1))


async def test_link_requires_claim(cardsvc):
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="qb"))
    with pytest.raises(CardServiceError):
        await cardsvc.svc.link(a, CreateLinkRequest(
            type="specializes", target_id=b, claim="  "))


async def test_link_idempotent_and_bumps_once(cardsvc):
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="qb"))
    r1 = await cardsvc.svc.link(a, CreateLinkRequest(
        type="specializes", target_id=b, claim="b narrows a"))
    r2 = await cardsvc.svc.link(a, CreateLinkRequest(
        type="specializes", target_id=b, claim="dup"))
    assert r1["link"] == r2["link"] == "l1"
    assert (await cardsvc.db.cards.get(a))["link_count"] == 1   # bumped once
    out = await cardsvc.db.card_links.list_out(a)
    assert len(out) == 1 and out[0]["target_type"] == "card"
    assert out[0]["claim"] == "b narrows a"   # original claim kept


async def test_link_related_canonicalized(cardsvc):
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa", card_id="card_aaa"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="qb", card_id="card_bbb"))
    # link from the larger id; stored under the smaller (canonical) subject
    r1 = await cardsvc.svc.link(b, CreateLinkRequest(
        type="related", target_id=a, claim="kin"))
    assert r1["card_id"] == "card_aaa" and r1["target_id"] == "card_bbb"
    # reverse direction dedupes to the same canonical row
    await cardsvc.svc.link(a, CreateLinkRequest(
        type="related", target_id=b, claim="kin"))
    assert len(await cardsvc.db.card_links.list_out("card_aaa")) == 1


async def test_link_source_writes_link_sessions(cardsvc):
    # ``--source`` on a link mirrors a Position's --source: one link_sessions
    # row per source, under the minted l<n>.
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="qb"))
    res = await cardsvc.svc.link(a, CreateLinkRequest(
        type="specializes", target_id=b, claim="b narrows a",
        source=[
            SourceRef(session_id=cardsvc.session, indexes="1-2"),
            SourceRef(session_id=cardsvc.session2, indexes="7"),
        ],
    ))
    link = res["link"]
    rows = await cardsvc.db.link_sessions.list_for_link(a, link)
    assert len(rows) == 2
    assert all(r["card_id"] == a and r["link"] == link for r in rows)
    assert {r["session_id"] for r in rows} == {cardsvc.session, cardsvc.session2}
    assert {r["indexes"] for r in rows} == {"1-2", "7"}
    # reverse lookup: which edges a session surfaced
    rev = await cardsvc.db.link_sessions.list_links_for_session(cardsvc.session)
    assert any(r["link"] == link for r in rev)


async def test_link_source_bad_session_rejected(cardsvc):
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="qb"))
    with pytest.raises(CardServiceError):
        await cardsvc.svc.link(a, CreateLinkRequest(
            type="specializes", target_id=b, claim="why",
            source=[SourceRef(session_id="sess-nope0000", indexes="1")],
        ))
    # rejected before any link_sessions write
    assert await cardsvc.db.card_links.list_out(a) == []


async def test_link_position_target_only_suggested_by(cardsvc):
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="qa"))
    with pytest.raises(CardServiceError):
        await cardsvc.svc.link(a, CreateLinkRequest(
            type="specializes", target_id="card_x#p1", claim="why"))
    # suggested_by → position target is allowed (dangling tolerated)
    r = await cardsvc.svc.link(a, CreateLinkRequest(
        type="suggested_by", target_id="card_x#p1", claim="that answer hinted this"))
    assert r["target_type"] == "position"

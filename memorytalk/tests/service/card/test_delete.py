"""CardService.delete_card — cascade hard-delete (escape hatch).

Covers the dry-run plan (deletes nothing), the full own-state cascade
(card row+dir, positions, reviews, outgoing links, all *_sessions
provenance), and the incoming-edge cascade (another card's edge pointing
at the deleted card is removed — row + source link file + that link's
link_sessions — while the source card's other data stays intact).

``cardsvc`` has ``search=None`` so vector deletes are exercised at the API
layer (``tests/api/test_card_api.py``) with the real dummy backend; here we
assert the SQLite + file cascade.
"""
from __future__ import annotations

import pytest

from memorytalk.schemas.card_requests import (
    CreateCardRequest, CreateLinkRequest, CreatePositionRequest,
    CreateReviewRequest, SourceRef,
)
from memorytalk.service.cards import CardNotFound


async def _populated_card(cardsvc):
    """A card with: 2 positions (one cited), 1 review, 1 outgoing link (cited).
    Returns (card_id, p1, p2, link)."""
    cid = await cardsvc.svc.create_card(CreateCardRequest(issue="Which db?"))
    p1 = await cardsvc.svc.add_position(cid, CreatePositionRequest(
        claim="SQLite", source=SourceRef(session_id=cardsvc.session, indexes="1-2")))
    p2 = await cardsvc.svc.add_position(cid, CreatePositionRequest(claim="LanceDB"))
    t = f"{cid}#{p1}"
    await cardsvc.svc.review(t, CreateReviewRequest(
        target=t, session_id=cardsvc.session, indexes="1", argument=1))
    other = await cardsvc.svc.create_card(CreateCardRequest(issue="other?"))
    res = await cardsvc.svc.link(cid, CreateLinkRequest(
        type="specializes", target_id=other, claim="narrows",
        source=[SourceRef(session_id=cardsvc.session, indexes="1")]))
    return cid, p1, p2, res["link"], other


async def test_dry_run_counts_and_deletes_nothing(cardsvc):
    cid, p1, p2, link, other = await _populated_card(cardsvc)
    # incoming edge: another card links AT cid
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="b?"))
    await cardsvc.svc.link(b, CreateLinkRequest(
        type="questions", target_id=cid, claim="why",
        source=[SourceRef(session_id=cardsvc.session, indexes="2")]))

    plan = await cardsvc.svc.delete_card(cid, dry_run=True)
    assert plan["card_id"] == cid and plan["issue"] == "Which db?"
    c = plan["counts"]
    assert c["positions"] == 2
    assert c["reviews"] == 1
    assert c["links_out"] == 1
    assert c["links_in"] == 1
    # provenance: 2 own link_sessions? -> p1 source(1) + own link source(1)
    #   + incoming link source(1) = 3
    assert c["provenance"] == 3
    assert c["vectors"] == 1 + 2   # card + 2 positions

    # nothing deleted
    assert await cardsvc.db.cards.exists(cid)
    assert await cardsvc.db.cards.read_doc(cid) is not None
    assert len(await cardsvc.db.positions.list_for_card(cid)) == 2


async def test_real_delete_cascades_own_state(cardsvc):
    cid, p1, p2, link, other = await _populated_card(cardsvc)

    res = await cardsvc.svc.delete_card(cid, dry_run=False)
    assert res["card_id"] == cid
    assert res["deleted"]["positions"] == 2

    # card row + dir gone
    assert not await cardsvc.db.cards.exists(cid)
    assert await cardsvc.db.cards.read_doc(cid) is None
    assert await cardsvc.db.positions.read_doc(cid, p1) is None
    assert await cardsvc.db.card_links.read_doc(cid, link) is None
    # subordinate rows gone
    assert await cardsvc.db.positions.list_for_card(cid) == []
    assert await cardsvc.db.reviews.list_for_card(cid) == []
    assert await cardsvc.db.card_links.list_out(cid) == []
    assert await cardsvc.db.card_sessions.list_for_card(cid) == []
    assert await cardsvc.db.position_sessions.list_for_position(cid, p1) == []
    assert await cardsvc.db.link_sessions.list_for_link(cid, link) == []
    # the OTHER (target) card is untouched
    assert await cardsvc.db.cards.exists(other)


async def test_incoming_edge_cascade_leaves_source_intact(cardsvc):
    # B links AT A; deleting A removes B's edge row + B's link file + that
    # link's link_sessions, but B itself (and its other state) stays.
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="A?"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="B?"))
    # B gets an unrelated position (must survive) + the incoming edge to A
    bp = await cardsvc.svc.add_position(b, CreatePositionRequest(claim="bclaim"))
    res = await cardsvc.svc.link(b, CreateLinkRequest(
        type="questions", target_id=a, claim="why a",
        source=[SourceRef(session_id=cardsvc.session, indexes="1")]))
    blink = res["link"]
    assert await cardsvc.db.card_links.read_doc(b, blink) is not None
    assert len(await cardsvc.db.link_sessions.list_for_link(b, blink)) == 1

    await cardsvc.svc.delete_card(a, dry_run=False)

    # B's incoming edge removed (row + file + provenance)
    assert await cardsvc.db.card_links.get(b, blink) is None
    assert await cardsvc.db.card_links.read_doc(b, blink) is None
    assert await cardsvc.db.link_sessions.list_for_link(b, blink) == []
    # B itself intact
    assert await cardsvc.db.cards.exists(b)
    assert await cardsvc.db.cards.read_doc(b) is not None
    assert (await cardsvc.db.positions.get(b, bp))["claim"] == "bclaim"


async def test_incoming_edge_to_fragment_address(cardsvc):
    # An edge targeting a SUBORDINATE address (card_id#p<n>) also counts as
    # incoming and is cascaded.
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="A?"))
    pa = await cardsvc.svc.add_position(a, CreatePositionRequest(claim="ans"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="B?"))
    res = await cardsvc.svc.link(b, CreateLinkRequest(
        type="suggested_by", target_id=f"{a}#{pa}", claim="from that answer"))
    blink = res["link"]

    plan = await cardsvc.svc.delete_card(a, dry_run=True)
    assert plan["counts"]["links_in"] == 1

    await cardsvc.svc.delete_card(a, dry_run=False)
    assert await cardsvc.db.card_links.get(b, blink) is None
    assert await cardsvc.db.cards.exists(b)


async def test_delete_unknown_card_raises_not_found(cardsvc):
    with pytest.raises(CardNotFound):
        await cardsvc.svc.delete_card("card_nope", dry_run=True)
    with pytest.raises(CardNotFound):
        await cardsvc.svc.delete_card("card_nope", dry_run=False)


async def test_self_edge_not_double_counted_as_incoming(cardsvc):
    # A related-to-itself style: a card's own outgoing edge must not appear
    # in links_in (subject == card_id excluded).
    a = await cardsvc.svc.create_card(CreateCardRequest(issue="A?"))
    b = await cardsvc.svc.create_card(CreateCardRequest(issue="B?"))
    await cardsvc.svc.link(a, CreateLinkRequest(
        type="specializes", target_id=b, claim="x"))
    plan = await cardsvc.svc.delete_card(a, dry_run=True)
    assert plan["counts"]["links_out"] == 1
    assert plan["counts"]["links_in"] == 0

"""v4 schemas -- models + defaults. See README.md."""
from __future__ import annotations

from memorytalk.schemas.card import Card, Position, CardLink, CardSession
from memorytalk.schemas.card_requests import (
    CreateCardRequest, CreatePositionRequest, CreateReviewRequest, CreateLinkRequest,
)


def test_position_defaults():
    p = Position(card_id="card_1", position="p1", claim="x", created_at="t")
    assert p.up_count == 0 and p.down_count == 0 and p.neutral_count == 0
    assert p.review_count == 0
    assert p.scope == ""
    assert p.forked_from is None


def test_card_defaults():
    c = Card(card_id="card_1", issue="why?", created_at="t")
    assert c.position_count == 0 and c.link_count == 0
    assert c.positions == [] and c.links == [] and c.sessions == []


def test_card_link_is_governed_object():
    e = CardLink(card_id="card_1", link="l1", type="specializes",
                 target_id="card_2", target_type="card",
                 claim="b narrows a", created_at="t")
    assert e.target_type == "card"
    assert e.link == "l1" and e.claim == "b narrows a"
    assert e.up_count == 0 and e.down_count == 0 and e.review_count == 0


def test_card_session_mark_defaults_empty():
    s = CardSession(card_id="card_1", session_id="sess-a", indexes="1-3", created_at="t")
    assert s.mark == ""


def test_create_card_request_optional_card_id():
    r = CreateCardRequest(issue="why?")
    assert r.card_id is None


def test_create_position_request_forked_from():
    r = CreatePositionRequest(claim="x", forked_from="p1")
    assert r.forked_from == "p1"


def test_create_review_target_and_argument():
    r = CreateReviewRequest(target="card_1#p1", session_id="sess-1",
                            indexes="1-3", argument=1)
    assert r.argument == 1 and r.target == "card_1#p1"


def test_create_link_request_requires_claim():
    r = CreateLinkRequest(type="specializes", target_id="card_2", claim="why")
    assert r.claim == "why"

"""v4 schemas -- models + defaults. See README.md."""
from __future__ import annotations

from memorytalk.schemas.card import Card, Position, CardLink, CardSession
from memorytalk.schemas.card_requests import (
    CreateCardRequest, CreatePositionRequest, CreateReviewRequest, CreateLinkRequest,
)


def test_position_defaults():
    p = Position(position_id="pos_1", card_id="card_1", claim="x", created_at="t")
    assert p.up_count == 0 and p.down_count == 0 and p.neutral_count == 0
    assert p.review_count == 0
    assert p.scope == ""
    assert p.forked_from_position_id is None


def test_card_defaults():
    c = Card(card_id="card_1", issue="why?", created_at="t")
    assert c.position_count == 0 and c.link_count == 0
    assert c.positions == [] and c.links == [] and c.sessions == []


def test_card_link_carries_target_type():
    e = CardLink(card_id="card_1", type="specializes",
                 target_id="card_2", target_type="card", created_at="t")
    assert e.target_type == "card"


def test_card_session_position_defaults_empty():
    s = CardSession(card_id="card_1", session_id="sess-a", indexes="1-3", created_at="t")
    assert s.position_id == ""


def test_create_card_request_optional_card_id():
    r = CreateCardRequest(issue="why?")
    assert r.card_id is None


def test_create_review_argument_literal():
    r = CreateReviewRequest(position_id="pos_1", session_id="sess-1",
                            indexes="1-3", argument=1)
    assert r.argument == 1

"""Log service: ASC-sorted events from per-object events.jsonl; 404 on missing."""
from __future__ import annotations

import pytest

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest, CreateLinkRequest,
    IngestRound, IngestSessionRequest,
)
from memorytalk.service import CardNotFound, SessionNotFound


async def _seed(services):
    sid = (await services.sessions.ingest(IngestSessionRequest(
        session_id="platform-aaa", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="hi")],
            is_sidechain=False,
        )],
    ))).session_id
    card_id = (await services.cards.create(CreateCardRequest(
        summary="s", rounds=[CardRoundsItem(session_id=sid, indexes="1")],
    ))).card_id
    await services.links.create(CreateLinkRequest(
        source_id=card_id, source_type="card",
        target_id=sid, target_type="session", comment="extracted",
    ))
    return sid, card_id


async def test_log_session_not_found(services):
    with pytest.raises(SessionNotFound):
        await services.sessions.log("sess_nope")


async def test_log_card_not_found(services):
    with pytest.raises(CardNotFound):
        await services.cards.log("card_nope")


async def test_log_session_events(services):
    sid, card_id = await _seed(services)
    r = await services.sessions.log(sid)
    assert r.type == "session"
    assert r.session_id == sid
    kinds = [e.kind for e in r.events]
    assert "imported" in kinds
    assert "card_extracted" in kinds
    assert "linked" in kinds


async def test_log_card_events(services):
    sid, card_id = await _seed(services)
    r = await services.cards.log(card_id)
    assert r.type == "card"
    assert r.card_id == card_id
    kinds = [e.kind for e in r.events]
    assert kinds == ["created", "linked"]

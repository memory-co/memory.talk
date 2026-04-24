"""Log service: ASC-sorted events from per-object events.jsonl; 404 on missing.

Prefix-dispatch now happens at the API layer; service-level tests call
CardService.log() and SessionService.log() directly.
"""
from __future__ import annotations

import pytest

from memory_talk_v2.service import CardNotFound, SessionNotFound


def _seed(services):
    sid = services.sessions.ingest(
        {"session_id": "platform-aaa", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "hi"}], "is_sidechain": False}]},
    )["session_id"]
    card_id = services.cards.create(
        {"summary": "s", "rounds": [{"session_id": sid, "indexes": "1"}]},
    )["card_id"]
    services.links.create(
        {"source_id": card_id, "source_type": "card",
         "target_id": sid, "target_type": "session", "comment": "extracted"},
    )
    return sid, card_id


def test_log_session_not_found(services):
    with pytest.raises(SessionNotFound):
        services.sessions.log("sess_nope")


def test_log_card_not_found(services):
    with pytest.raises(CardNotFound):
        services.cards.log("card_nope")


def test_log_session_events(services):
    sid, card_id = _seed(services)
    r = services.sessions.log(sid)
    assert r["type"] == "session"
    assert r["session_id"] == sid
    kinds = [e["kind"] for e in r["events"]]
    assert "imported" in kinds
    assert "card_extracted" in kinds
    assert "linked" in kinds


def test_log_card_events(services):
    sid, card_id = _seed(services)
    r = services.cards.log(card_id)
    assert r["type"] == "card"
    assert r["card_id"] == card_id
    kinds = [e["kind"] for e in r["events"]]
    assert kinds == ["created", "linked"]

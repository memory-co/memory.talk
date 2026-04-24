"""User link creation: prefix checks, self-loop, two-end events."""
from __future__ import annotations

import pytest

from memory_talk_v2.service import LinkNotFoundError, LinkServiceError


def _seed(services):
    ingest = services.sessions.ingest(
        {"session_id": "platform-abc", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "hi"}], "is_sidechain": False}]},
    )
    sid = ingest["session_id"]
    card1 = services.cards.create(
        {"summary": "one", "rounds": [{"session_id": sid, "indexes": "1"}]},
    )["card_id"]
    card2 = services.cards.create(
        {"summary": "two", "rounds": [{"session_id": sid, "indexes": "1"}]},
    )["card_id"]
    return sid, card1, card2


def test_create_user_link_card_to_card(services):
    sid, card1, card2 = _seed(services)
    r = services.links.create(
        {"source_id": card1, "source_type": "card",
         "target_id": card2, "target_type": "card", "comment": "followup"},
    )
    assert r["status"] == "ok"
    assert r["ttl"] == services.config.settings.ttl.link.initial

    link = services.db.get_link(r["link_id"])
    assert link["source_id"] == card1 and link["target_id"] == card2
    assert link["expires_at"] is not None

    outgoing = [e for e in services.events_for(card1)
                if e["kind"] == "linked" and e["detail"]["direction"] == "outgoing"]
    incoming = [e for e in services.events_for(card2)
                if e["kind"] == "linked" and e["detail"]["direction"] == "incoming"]
    assert len(outgoing) == 1
    assert len(incoming) == 1
    assert outgoing[0]["detail"]["link_id"] == r["link_id"]
    assert outgoing[0]["detail"]["peer_id"] == card2


def test_self_loop_rejected(services):
    sid, card1, _ = _seed(services)
    with pytest.raises(LinkServiceError, match="self-loop"):
        services.links.create(
            {"source_id": card1, "source_type": "card",
             "target_id": card1, "target_type": "card", "comment": None},
        )


def test_type_mismatch_rejected(services):
    sid, card1, _ = _seed(services)
    with pytest.raises(LinkServiceError):
        services.links.create(
            {"source_id": card1, "source_type": "session",
             "target_id": sid, "target_type": "session", "comment": None},
        )


def test_missing_target_raises_not_found(services):
    sid, card1, _ = _seed(services)
    with pytest.raises(LinkNotFoundError):
        services.links.create(
            {"source_id": card1, "source_type": "card",
             "target_id": "card_does_not_exist", "target_type": "card", "comment": None},
        )


def test_long_comment_rejected(services):
    sid, card1, card2 = _seed(services)
    services.config._settings.search.comment_max_length = 10
    with pytest.raises(LinkServiceError, match="too long"):
        services.links.create(
            {"source_id": card1, "source_type": "card",
             "target_id": card2, "target_type": "card", "comment": "x" * 50},
        )

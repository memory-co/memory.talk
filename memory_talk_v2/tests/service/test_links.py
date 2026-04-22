"""User link creation: prefix checks, self-loop, two-end events."""
from __future__ import annotations

import pytest

from memory_talk_v2.service.cards import create_card
from memory_talk_v2.service.links import (
    LinkNotFoundError, LinkServiceError, create_user_link,
)
from memory_talk_v2.service.sessions import ingest_session


def _seed(services):
    ingest = ingest_session(
        {"session_id": "platform-abc", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "hi"}], "is_sidechain": False}]},
        db=services.db, vectors=services.vectors, events=services.events,
        sessions_root=services.config.sessions_dir,
    )
    sid = ingest["session_id"]
    card1 = create_card(
        {"summary": "one", "rounds": [{"session_id": sid, "indexes": "1"}]},
        config=services.config, db=services.db, vectors=services.vectors,
        embedder=services.embedder, events=services.events,
    )["card_id"]
    card2 = create_card(
        {"summary": "two", "rounds": [{"session_id": sid, "indexes": "1"}]},
        config=services.config, db=services.db, vectors=services.vectors,
        embedder=services.embedder, events=services.events,
    )["card_id"]
    return sid, card1, card2


def test_create_user_link_card_to_card(services):
    sid, card1, card2 = _seed(services)
    r = create_user_link(
        {"source_id": card1, "source_type": "card",
         "target_id": card2, "target_type": "card", "comment": "followup"},
        config=services.config, db=services.db, events=services.events,
    )
    assert r["status"] == "ok"
    assert r["ttl"] == services.config.settings.ttl.link.initial

    link = services.db.get_link(r["link_id"])
    assert link["source_id"] == card1 and link["target_id"] == card2
    assert link["expires_at"] is not None  # user link has TTL

    # Two-end events
    outgoing = [e for e in services.db.events_for(card1)
                if e["kind"] == "linked" and e["detail"]["direction"] == "outgoing"]
    incoming = [e for e in services.db.events_for(card2)
                if e["kind"] == "linked" and e["detail"]["direction"] == "incoming"]
    assert len(outgoing) == 1
    assert len(incoming) == 1
    assert outgoing[0]["detail"]["link_id"] == r["link_id"]
    assert outgoing[0]["detail"]["peer_id"] == card2


def test_self_loop_rejected(services):
    sid, card1, _ = _seed(services)
    with pytest.raises(LinkServiceError, match="self-loop"):
        create_user_link(
            {"source_id": card1, "source_type": "card",
             "target_id": card1, "target_type": "card", "comment": None},
            config=services.config, db=services.db, events=services.events,
        )


def test_type_mismatch_rejected(services):
    sid, card1, _ = _seed(services)
    with pytest.raises(LinkServiceError):
        create_user_link(
            {"source_id": card1, "source_type": "session",  # type lies
             "target_id": sid, "target_type": "session", "comment": None},
            config=services.config, db=services.db, events=services.events,
        )


def test_missing_target_raises_not_found(services):
    sid, card1, _ = _seed(services)
    with pytest.raises(LinkNotFoundError):
        create_user_link(
            {"source_id": card1, "source_type": "card",
             "target_id": "card_does_not_exist", "target_type": "card", "comment": None},
            config=services.config, db=services.db, events=services.events,
        )


def test_long_comment_rejected(services):
    sid, card1, card2 = _seed(services)
    services.config._settings.search.comment_max_length = 10
    with pytest.raises(LinkServiceError, match="too long"):
        create_user_link(
            {"source_id": card1, "source_type": "card",
             "target_id": card2, "target_type": "card", "comment": "x" * 50},
            config=services.config, db=services.db, events=services.events,
        )

"""Log service: prefix dispatch, 404 on missing, sorted ASC."""
from __future__ import annotations
import pytest

from memory_talk_v2.service.cards import create_card
from memory_talk_v2.service.links import create_user_link
from memory_talk_v2.service.log import LogError, LogNotFound, log
from memory_talk_v2.service.sessions import ingest_session


def _seed(services):
    sid = ingest_session(
        {"session_id": "platform-aaa", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "hi"}], "is_sidechain": False}]},
        db=services.db, vectors=services.vectors, events=services.events,
        sessions_root=services.config.sessions_dir,
    )["session_id"]
    card_id = create_card(
        {"summary": "s", "rounds": [{"session_id": sid, "indexes": "1"}]},
        config=services.config, db=services.db, vectors=services.vectors,
        embedder=services.embedder, events=services.events,
    )["card_id"]
    create_user_link(
        {"source_id": card_id, "source_type": "card",
         "target_id": sid, "target_type": "session", "comment": "extracted"},
        config=services.config, db=services.db, events=services.events,
    )
    return sid, card_id


def test_log_invalid_prefix(services):
    with pytest.raises(LogError):
        log("foo_bar", db=services.db)


def test_log_not_found(services):
    with pytest.raises(LogNotFound):
        log("card_nope", db=services.db)


def test_log_session_events(services):
    sid, card_id = _seed(services)
    r = log(sid, db=services.db)
    assert r["type"] == "session"
    assert r["session_id"] == sid
    kinds = [e["kind"] for e in r["events"]]
    # Should include imported, card_extracted, linked
    assert "imported" in kinds
    assert "card_extracted" in kinds
    assert "linked" in kinds


def test_log_card_events(services):
    sid, card_id = _seed(services)
    r = log(card_id, db=services.db)
    assert r["type"] == "card"
    assert r["card_id"] == card_id
    kinds = [e["kind"] for e in r["events"]]
    assert kinds == ["created", "linked"]  # order by `at` ASC

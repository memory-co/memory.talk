"""View semantics: prefix dispatch, card TTL refresh, user link refresh, expired sentinel."""
from __future__ import annotations
from datetime import timedelta

import pytest

from memory_talk_v2.service.cards import create_card
from memory_talk_v2.service.links import create_user_link
from memory_talk_v2.service.sessions import ingest_session
from memory_talk_v2.service.ttl import iso_to_dt, now_utc
from memory_talk_v2.service.view import ViewError, ViewNotFound, view


def _seed(services):
    ingest = ingest_session(
        {"session_id": "platform-xyz", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "hi"}], "is_sidechain": False}]},
        db=services.db, vectors=services.vectors, events=services.events,
        sessions_root=services.config.sessions_dir,
    )
    sid = ingest["session_id"]
    card_id = create_card(
        {"summary": "s", "rounds": [{"session_id": sid, "indexes": "1"}]},
        config=services.config, db=services.db, vectors=services.vectors,
        embedder=services.embedder, events=services.events,
    )["card_id"]
    return sid, card_id


def test_view_invalid_prefix(services):
    with pytest.raises(ViewError):
        view("foo_bar", config=services.config, db=services.db)


def test_view_not_found(services):
    with pytest.raises(ViewNotFound):
        view("card_nope", config=services.config, db=services.db)


def test_view_card_refreshes_ttl(services):
    sid, card_id = _seed(services)
    before = services.db.get_card(card_id)["expires_at"]
    result = view(card_id, config=services.config, db=services.db)
    assert result["type"] == "card"
    assert result["card"]["card_id"] == card_id
    # The returned ttl is positive and the card's expires_at has advanced
    assert result["card"]["ttl"] > 0
    after = services.db.get_card(card_id)["expires_at"]
    assert iso_to_dt(after) > iso_to_dt(before)
    # Default link present with ttl = 0 sentinel
    default_links = [l for l in result["links"] if l["ttl"] == 0]
    assert default_links and default_links[0]["target_id"] == sid


def test_view_session_no_ttl_change(services):
    sid, _ = _seed(services)
    result = view(sid, config=services.config, db=services.db)
    assert result["type"] == "session"
    assert result["session"]["session_id"] == sid
    assert result["session"]["rounds"][0]["index"] == 1


def test_view_refreshes_user_link(services):
    sid, card_id = _seed(services)
    # Attach a user link
    create_user_link(
        {"source_id": card_id, "source_type": "card",
         "target_id": sid, "target_type": "session", "comment": "x"},
        config=services.config, db=services.db, events=services.events,
    )
    # Find user link
    links = [l for l in services.db.links_touching(card_id) if l["expires_at"] is not None]
    assert len(links) == 1
    before_exp = links[0]["expires_at"]

    view(card_id, config=services.config, db=services.db)

    after_exp = services.db.get_link(links[0]["link_id"])["expires_at"]
    assert iso_to_dt(after_exp) > iso_to_dt(before_exp)


def test_view_does_not_revive_expired_link(services):
    sid, card_id = _seed(services)
    r = create_user_link(
        {"source_id": card_id, "source_type": "card",
         "target_id": sid, "target_type": "session", "comment": "x"},
        config=services.config, db=services.db, events=services.events,
    )
    # Force-expire the user link
    from memory_talk_v2.service.ttl import dt_to_iso
    past = dt_to_iso(now_utc() - timedelta(seconds=1000))
    services.db.update_link_expires_at(r["link_id"], past)

    view(card_id, config=services.config, db=services.db)

    still_expired = services.db.get_link(r["link_id"])["expires_at"]
    assert still_expired == past   # not refreshed

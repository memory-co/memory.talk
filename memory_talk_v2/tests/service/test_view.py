"""View semantics: TTL refresh, user-link refresh, expired sentinel.

Prefix-dispatch (e.g. rejecting foo_bar) is now the API handler's job;
service-level tests exercise CardService.view() and SessionService.view()
directly.
"""
from __future__ import annotations
from datetime import timedelta

import pytest

from memory_talk_v2.service import (
    CardNotFound, CardServiceError, SessionNotFound, SessionServiceError,
)
from memory_talk_v2.service.ttl import dt_to_iso, iso_to_dt, now_utc


def _seed(services):
    ingest = services.sessions.ingest(
        {"session_id": "platform-xyz", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "hi"}], "is_sidechain": False}]},
    )
    sid = ingest["session_id"]
    card_id = services.cards.create(
        {"summary": "s", "rounds": [{"session_id": sid, "indexes": "1"}]},
    )["card_id"]
    return sid, card_id


def test_view_card_bad_prefix(services):
    with pytest.raises(CardServiceError):
        services.cards.view("sess_nope")


def test_view_session_bad_prefix(services):
    with pytest.raises(SessionServiceError):
        services.sessions.view("card_nope")


def test_view_card_not_found(services):
    with pytest.raises(CardNotFound):
        services.cards.view("card_nope")


def test_view_session_not_found(services):
    with pytest.raises(SessionNotFound):
        services.sessions.view("sess_nope")


def test_view_card_refreshes_ttl(services):
    sid, card_id = _seed(services)
    before = services.db.get_card(card_id)["expires_at"]
    result = services.cards.view(card_id)
    assert result["type"] == "card"
    assert result["card"]["card_id"] == card_id
    assert result["card"]["ttl"] > 0
    after = services.db.get_card(card_id)["expires_at"]
    assert iso_to_dt(after) > iso_to_dt(before)

    default_links = [l for l in result["links"] if l["ttl"] == 0]
    assert default_links and default_links[0]["target_id"] == sid


def test_view_session_no_ttl_change(services):
    sid, _ = _seed(services)
    result = services.sessions.view(sid)
    assert result["type"] == "session"
    assert result["session"]["session_id"] == sid
    assert result["session"]["rounds"][0]["index"] == 1


def test_view_refreshes_user_link(services):
    sid, card_id = _seed(services)
    services.links.create(
        {"source_id": card_id, "source_type": "card",
         "target_id": sid, "target_type": "session", "comment": "x"},
    )
    links = [l for l in services.db.links_touching(card_id) if l["expires_at"] is not None]
    assert len(links) == 1
    before_exp = links[0]["expires_at"]

    services.cards.view(card_id)

    after_exp = services.db.get_link(links[0]["link_id"])["expires_at"]
    assert iso_to_dt(after_exp) > iso_to_dt(before_exp)


def test_view_does_not_revive_expired_link(services):
    sid, card_id = _seed(services)
    r = services.links.create(
        {"source_id": card_id, "source_type": "card",
         "target_id": sid, "target_type": "session", "comment": "x"},
    )
    past = dt_to_iso(now_utc() - timedelta(seconds=1000))
    services.db.update_link_expires_at(r["link_id"], past)

    services.cards.view(card_id)

    still_expired = services.db.get_link(r["link_id"])["expires_at"]
    assert still_expired == past

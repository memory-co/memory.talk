"""Session tags: diff-based events, idempotency, now owned by SessionService."""
from __future__ import annotations

import pytest

from memory_talk_v2.service import SessionNotFound, SessionServiceError


def _seed_session(services):
    return services.sessions.ingest(
        {"session_id": "platform-abc", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "x"}], "is_sidechain": False}]},
    )["session_id"]


def test_add_tags_emits_per_new_tag(services):
    sid = _seed_session(services)
    r = services.sessions.add_tags({"session_id": sid, "tags": ["a", "b"]})
    assert r["tags"] == ["a", "b"]
    kinds = [e["kind"] for e in services.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added", "tag_added"]


def test_add_tags_idempotent(services):
    sid = _seed_session(services)
    services.sessions.add_tags({"session_id": sid, "tags": ["a"]})
    r = services.sessions.add_tags({"session_id": sid, "tags": ["a"]})
    assert r["tags"] == ["a"]
    kinds = [e["kind"] for e in services.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added"]


def test_remove_tags_emits_per_real_removal(services):
    sid = _seed_session(services)
    services.sessions.add_tags({"session_id": sid, "tags": ["a", "b"]})
    r = services.sessions.remove_tags({"session_id": sid, "tags": ["b", "c"]})
    assert r["tags"] == ["a"]
    kinds = [e["kind"] for e in services.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added", "tag_added", "tag_removed"]


def test_card_id_prefix_rejected(services):
    with pytest.raises(SessionServiceError, match="type mismatch"):
        services.sessions.add_tags({"session_id": "card_nope", "tags": ["a"]})


def test_missing_session_404(services):
    with pytest.raises(SessionNotFound):
        services.sessions.add_tags({"session_id": "sess_nope", "tags": ["a"]})

"""Session tags: diff-based events, idempotency."""
from __future__ import annotations

import pytest

from memory_talk_v2.service.sessions import ingest_session
from memory_talk_v2.service.tags import (
    TagNotFoundError, TagServiceError, add_tags, remove_tags,
)


def _seed_session(services):
    return ingest_session(
        {"session_id": "platform-abc", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "x"}], "is_sidechain": False}]},
        db=services.db, vectors=services.vectors, events=services.events,
        sessions_root=services.config.sessions_dir,
    )["session_id"]


def test_add_tags_emits_per_new_tag(services):
    sid = _seed_session(services)
    r = add_tags({"session_id": sid, "tags": ["a", "b"]},
                 db=services.db, events=services.events,
                 sessions_root=services.config.sessions_dir)
    assert r["tags"] == ["a", "b"]
    kinds = [e["kind"] for e in services.db.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added", "tag_added"]


def test_add_tags_idempotent(services):
    sid = _seed_session(services)
    add_tags({"session_id": sid, "tags": ["a"]},
             db=services.db, events=services.events,
             sessions_root=services.config.sessions_dir)
    r = add_tags({"session_id": sid, "tags": ["a"]},  # duplicate
                 db=services.db, events=services.events,
                 sessions_root=services.config.sessions_dir)
    assert r["tags"] == ["a"]
    kinds = [e["kind"] for e in services.db.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added"]  # only one event


def test_remove_tags_emits_per_real_removal(services):
    sid = _seed_session(services)
    add_tags({"session_id": sid, "tags": ["a", "b"]},
             db=services.db, events=services.events,
             sessions_root=services.config.sessions_dir)
    r = remove_tags({"session_id": sid, "tags": ["b", "c"]},
                    db=services.db, events=services.events,
                    sessions_root=services.config.sessions_dir)
    assert r["tags"] == ["a"]
    kinds = [e["kind"] for e in services.db.events_for(sid) if e["kind"].startswith("tag_")]
    # a(added), b(added), b(removed) — not c, because it wasn't present
    assert kinds == ["tag_added", "tag_added", "tag_removed"]


def test_card_id_prefix_rejected(services):
    with pytest.raises(TagServiceError, match="type mismatch"):
        add_tags({"session_id": "card_nope", "tags": ["a"]},
                 db=services.db, events=services.events,
                 sessions_root=services.config.sessions_dir)


def test_missing_session_404(services):
    with pytest.raises(TagNotFoundError):
        add_tags({"session_id": "sess_nope", "tags": ["a"]},
                 db=services.db, events=services.events,
                 sessions_root=services.config.sessions_dir)

"""Session tags: diff-based events, idempotency."""
from __future__ import annotations

import pytest

from memory_talk_v2.service import SessionNotFound, SessionServiceError


async def _seed_session(services):
    return (await services.sessions.ingest(
        {"session_id": "platform-abc", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "x"}], "is_sidechain": False}]},
    ))["session_id"]


async def test_add_tags_emits_per_new_tag(services):
    sid = await _seed_session(services)
    r = await services.sessions.add_tags({"session_id": sid, "tags": ["a", "b"]})
    assert r["tags"] == ["a", "b"]
    kinds = [e["kind"] for e in await services.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added", "tag_added"]


async def test_add_tags_idempotent(services):
    sid = await _seed_session(services)
    await services.sessions.add_tags({"session_id": sid, "tags": ["a"]})
    r = await services.sessions.add_tags({"session_id": sid, "tags": ["a"]})
    assert r["tags"] == ["a"]
    kinds = [e["kind"] for e in await services.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added"]


async def test_remove_tags_emits_per_real_removal(services):
    sid = await _seed_session(services)
    await services.sessions.add_tags({"session_id": sid, "tags": ["a", "b"]})
    r = await services.sessions.remove_tags({"session_id": sid, "tags": ["b", "c"]})
    assert r["tags"] == ["a"]
    kinds = [e["kind"] for e in await services.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added", "tag_added", "tag_removed"]


async def test_card_id_prefix_rejected(services):
    with pytest.raises(SessionServiceError, match="type mismatch"):
        await services.sessions.add_tags({"session_id": "card_nope", "tags": ["a"]})


async def test_missing_session_404(services):
    with pytest.raises(SessionNotFound):
        await services.sessions.add_tags({"session_id": "sess_nope", "tags": ["a"]})

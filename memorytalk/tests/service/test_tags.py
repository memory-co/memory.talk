"""Session tags: diff-based events, idempotency."""
from __future__ import annotations

import pytest

from memorytalk.schemas import ContentBlock, IngestRound, IngestSessionRequest, TagsRequest
from memorytalk.service import SessionNotFound, SessionServiceError


async def _seed_session(services):
    r = await services.sessions.ingest(IngestSessionRequest(
        session_id="platform-abc", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="x")],
            is_sidechain=False,
        )],
    ))
    return r.session_id


async def test_add_tags_emits_per_new_tag(services):
    sid = await _seed_session(services)
    r = await services.sessions.add_tags(TagsRequest(session_id=sid, tags=["a", "b"]))
    assert r.tags == ["a", "b"]
    kinds = [e["kind"] for e in await services.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added", "tag_added"]


async def test_add_tags_idempotent(services):
    sid = await _seed_session(services)
    await services.sessions.add_tags(TagsRequest(session_id=sid, tags=["a"]))
    r = await services.sessions.add_tags(TagsRequest(session_id=sid, tags=["a"]))
    assert r.tags == ["a"]
    kinds = [e["kind"] for e in await services.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added"]


async def test_remove_tags_emits_per_real_removal(services):
    sid = await _seed_session(services)
    await services.sessions.add_tags(TagsRequest(session_id=sid, tags=["a", "b"]))
    r = await services.sessions.remove_tags(TagsRequest(session_id=sid, tags=["b", "c"]))
    assert r.tags == ["a"]
    kinds = [e["kind"] for e in await services.events_for(sid) if e["kind"].startswith("tag_")]
    assert kinds == ["tag_added", "tag_added", "tag_removed"]


async def test_card_id_prefix_rejected(services):
    with pytest.raises(SessionServiceError, match="type mismatch"):
        await services.sessions.add_tags(TagsRequest(session_id="card_nope", tags=["a"]))


async def test_missing_session_404(services):
    with pytest.raises(SessionNotFound):
        await services.sessions.add_tags(TagsRequest(session_id="sess_nope", tags=["a"]))

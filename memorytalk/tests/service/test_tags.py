"""TagService — kv tags on session/card subjects, with three event kinds.

Covers:
- happy path add (session + card)
- upsert: same value → noop, different value → tag_updated with prior_value
- remove by key (value part of input ignored; only matches by key)
- idempotent remove (missing key → no event)
- empty input rejected
- subject_id prefix invalid → TagServiceError
- subject not found → SessionNotFound
- value-with-colon and empty-value parsing
- tags.json mirror written on disk (matches sqlite)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest,
    IngestRound, IngestSessionRequest,
)
from memorytalk.service import SessionNotFound, TagServiceError


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
    # ingest() auto-stamps `sync_session: new` for the new-session filter.
    # These tests are about tag ops in isolation, so strip it.
    await services.tags.remove_tags(r.session_id, ["sync_session"])
    return r.session_id


async def _seed_card(services):
    sid = await _seed_session(services)
    r = await services.cards.create(CreateCardRequest(
        summary="card for tag tests",
        rounds=[CardRoundsItem(session_id=sid, indexes="1")],
    ))
    return r.card_id


def _values(resp) -> list[tuple[str, str]]:
    return [(p.key, p.value) for p in resp.tags]


def _tag_events(events: list[dict]) -> list[dict]:
    """Filter to tag_* events excluding sync_session (auto-stamped + seed cleanup noise)."""
    return [
        e for e in events
        if e["kind"].startswith("tag_") and e.get("detail", {}).get("key") != "sync_session"
    ]


# -------- happy path: add --------

async def test_add_kv_tag_on_session(services):
    sid = await _seed_session(services)
    r = await services.tags.add_tags(sid, ["project:memory-talk", "decision"])
    assert _values(r) == [("project", "memory-talk"), ("decision", "")]
    kinds = [e["kind"] for e in _tag_events(await services.events_for(sid))]
    assert kinds == ["tag_added", "tag_added"]


async def test_add_kv_tag_on_card(services):
    cid = await _seed_card(services)
    r = await services.tags.add_tags(cid, ["topic:lancedb", "status:reviewed"])
    assert _values(r) == [("topic", "lancedb"), ("status", "reviewed")]
    kinds = [e["kind"] for e in _tag_events(await services.events_for(cid))]
    assert kinds == ["tag_added", "tag_added"]


# -------- upsert: same vs different value --------

async def test_add_existing_key_same_value_is_noop(services):
    sid = await _seed_session(services)
    await services.tags.add_tags(sid, ["project:memory-talk"])
    r = await services.tags.add_tags(sid, ["project:memory-talk"])
    assert _values(r) == [("project", "memory-talk")]
    kinds = [e["kind"] for e in _tag_events(await services.events_for(sid))]
    assert kinds == ["tag_added"]  # only first add emitted


async def test_add_existing_key_new_value_emits_updated(services):
    sid = await _seed_session(services)
    await services.tags.add_tags(sid, ["project:foo"])
    r = await services.tags.add_tags(sid, ["project:bar"])
    assert _values(r) == [("project", "bar")]
    events = _tag_events(await services.events_for(sid))
    assert [e["kind"] for e in events] == ["tag_added", "tag_updated"]
    assert events[1]["detail"] == {"key": "project", "value": "bar", "prior_value": "foo"}


async def test_seq_preserves_insertion_order(services):
    sid = await _seed_session(services)
    await services.tags.add_tags(sid, ["a", "b", "c"])
    # Updating b should NOT change its position
    r = await services.tags.add_tags(sid, ["b:newval"])
    assert _values(r) == [("a", ""), ("b", "newval"), ("c", "")]


# -------- remove --------

async def test_remove_by_key(services):
    sid = await _seed_session(services)
    await services.tags.add_tags(sid, ["project:foo", "decision"])
    r = await services.tags.remove_tags(sid, ["project"])
    assert _values(r) == [("decision", "")]
    events = [e for e in await services.events_for(sid) if e["kind"].startswith("tag_")]
    assert events[-1]["kind"] == "tag_removed"
    assert events[-1]["detail"] == {"key": "project", "value": "foo"}


async def test_remove_nonexistent_key_is_idempotent(services):
    sid = await _seed_session(services)
    await services.tags.add_tags(sid, ["a"])
    r = await services.tags.remove_tags(sid, ["never-was-here"])
    assert _values(r) == [("a", "")]
    kinds = [e["kind"] for e in _tag_events(await services.events_for(sid))
             if e["kind"] == "tag_removed"]
    assert kinds == []


# -------- value parsing edge cases --------

async def test_value_with_colon_split_on_first(services):
    sid = await _seed_session(services)
    r = await services.tags.add_tags(sid, ["path:/etc/hosts:rw"])
    assert _values(r) == [("path", "/etc/hosts:rw")]


async def test_empty_value_when_no_colon(services):
    sid = await _seed_session(services)
    r = await services.tags.add_tags(sid, ["decision"])
    assert _values(r) == [("decision", "")]


async def test_trailing_colon_yields_empty_value(services):
    sid = await _seed_session(services)
    r = await services.tags.add_tags(sid, ["version:"])
    assert _values(r) == [("version", "")]


async def test_empty_key_rejected(services):
    sid = await _seed_session(services)
    with pytest.raises(TagServiceError, match="key cannot be empty"):
        await services.tags.add_tags(sid, [":justvalue"])


# -------- error paths --------

async def test_invalid_subject_prefix_rejected(services):
    with pytest.raises(TagServiceError, match="sess_ or card_"):
        await services.tags.add_tags("foo_x", ["a"])


async def test_subject_not_found_404(services):
    with pytest.raises(SessionNotFound):
        await services.tags.add_tags("sess_does_not_exist", ["a"])


async def test_card_subject_not_found_404(services):
    with pytest.raises(SessionNotFound):
        await services.tags.add_tags("card_does_not_exist", ["a"])


async def test_empty_tags_list_rejected(services):
    sid = await _seed_session(services)
    with pytest.raises(TagServiceError, match="non-empty"):
        await services.tags.add_tags(sid, [])


async def test_empty_keys_list_rejected_on_remove(services):
    sid = await _seed_session(services)
    with pytest.raises(TagServiceError, match="non-empty"):
        await services.tags.remove_tags(sid, [])


# -------- tags.json mirror --------

async def test_tags_json_mirror_written_on_session(services, tmp_path: Path):
    sid = await _seed_session(services)
    await services.tags.add_tags(sid, ["project:memory-talk", "decision"])
    bucket = sid[len("sess_"):][:2].lower()
    path = services.config.data_root / "sessions" / "claude-code" / bucket / sid / "tags.json"
    body = json.loads(path.read_text())
    assert body == {"project": "memory-talk", "decision": ""}


async def test_tags_json_mirror_deleted_when_all_removed(services):
    sid = await _seed_session(services)
    await services.tags.add_tags(sid, ["a"])
    bucket = sid[len("sess_"):][:2].lower()
    path = services.config.data_root / "sessions" / "claude-code" / bucket / sid / "tags.json"
    assert path.exists()
    await services.tags.remove_tags(sid, ["a"])
    assert not path.exists()


async def test_tags_json_mirror_written_on_card(services):
    cid = await _seed_card(services)
    await services.tags.add_tags(cid, ["topic:lancedb"])
    bucket = cid[len("card_"):][:2].lower()
    path = services.config.data_root / "cards" / bucket / cid / "tags.json"
    body = json.loads(path.read_text())
    assert body == {"topic": "lancedb"}

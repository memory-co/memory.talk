"""IngestService cursor-based protocol: ensure_session + append_rounds.

These tests bypass HTTP and call the service methods directly. The
optimistic-concurrency contract is the new spine of sync — if these
properties break, sync's conflict handling and dedup both fall apart.
"""
from __future__ import annotations
import pytest

from memorytalk.schemas import (
    AppendRoundsRequest, ContentBlock, EnsureSessionRequest, RoundInput,
)


pytestmark = pytest.mark.asyncio


def _round(rid: str, text: str, role: str = "human") -> RoundInput:
    return RoundInput(
        round_id=rid, role=role,
        content=[ContentBlock(type="text", text=text)],
    )


async def test_ensure_session_returns_none_for_unknown(app):
    res = await app.state.ingest.ensure_session(EnsureSessionRequest(
        source="claude-code", session_id="never-seen",
    ))
    assert res.session_id == "sess_never-seen"
    assert res.last_round_id is None
    assert res.round_count == 0


async def test_append_rounds_first_call_creates_session(app):
    """expected_prev_round_id=None on a brand-new session writes the row
    and returns the last round_id as new_last."""
    res = await app.state.ingest.append_rounds(AppendRoundsRequest(
        session_id="abc", source="claude-code",
        expected_prev_round_id=None,
        rounds=[_round("r1", "one"), _round("r2", "two")],
        created_at="2026-05-20T00:00:00Z",
        metadata={"cwd": "/work"},
    ))
    assert res.status == "ok"
    assert res.session_id == "sess_abc"
    assert res.new_last_round_id == "r2"
    assert res.appended_count == 2
    assert res.round_count == 2

    # ensure_session now reflects the persisted cursor.
    e = await app.state.ingest.ensure_session(EnsureSessionRequest(
        source="claude-code", session_id="abc",
    ))
    assert e.last_round_id == "r2"
    assert e.round_count == 2


async def test_append_rounds_subsequent_call_extends_cursor(app):
    await app.state.ingest.append_rounds(AppendRoundsRequest(
        session_id="abc", source="claude-code",
        expected_prev_round_id=None,
        rounds=[_round("r1", "one")],
        created_at="2026-05-20T00:00:00Z",
        metadata={"cwd": "/work"},
    ))
    res = await app.state.ingest.append_rounds(AppendRoundsRequest(
        session_id="abc", source="claude-code",
        expected_prev_round_id="r1",
        rounds=[_round("r2", "two"), _round("r3", "three")],
        created_at="2026-05-20T00:00:00Z",
        metadata={"cwd": "/work"},
    ))
    assert res.status == "ok"
    assert res.new_last_round_id == "r3"
    assert res.appended_count == 2
    assert res.round_count == 3


async def test_append_rounds_cursor_mismatch_returns_conflict(app):
    """When expected_prev_round_id doesn't match the server's stored
    last_round_id, the response surfaces ``status="conflict"`` with the
    server's actual cursor — sync uses that to recompute and retry."""
    await app.state.ingest.append_rounds(AppendRoundsRequest(
        session_id="abc", source="claude-code",
        expected_prev_round_id=None,
        rounds=[_round("r1", "one"), _round("r2", "two")],
        created_at="2026-05-20T00:00:00Z",
        metadata={"cwd": "/work"},
    ))

    # Caller thinks they're still at None — but server has r2.
    res = await app.state.ingest.append_rounds(AppendRoundsRequest(
        session_id="abc", source="claude-code",
        expected_prev_round_id=None,
        rounds=[_round("r3", "three")],
        created_at="2026-05-20T00:00:00Z",
        metadata={"cwd": "/work"},
    ))
    assert res.status == "conflict"
    assert res.actual_last_round_id == "r2"
    assert res.appended_count == 0


async def test_append_rounds_existing_session_with_none_cursor_conflicts(app):
    """An adapter-side bug or a stale checkpoint shouldn't be able to
    'reset' a session. expected_prev_round_id=None against an existing
    cursor must conflict, not silently re-import."""
    await app.state.ingest.append_rounds(AppendRoundsRequest(
        session_id="abc", source="claude-code",
        expected_prev_round_id=None,
        rounds=[_round("r1", "one")],
        created_at="2026-05-20T00:00:00Z",
        metadata={"cwd": "/work"},
    ))
    res = await app.state.ingest.append_rounds(AppendRoundsRequest(
        session_id="abc", source="claude-code",
        expected_prev_round_id=None,
        rounds=[_round("rX", "wrong tree")],
        created_at="2026-05-20T00:00:00Z",
        metadata={"cwd": "/work"},
    ))
    assert res.status == "conflict"
    assert res.actual_last_round_id == "r1"


async def test_append_rounds_empty_with_matching_cursor_is_noop(app):
    """If the caller's cursor matches but they have nothing new to add,
    the call succeeds with appended_count=0 and the cursor unchanged."""
    await app.state.ingest.append_rounds(AppendRoundsRequest(
        session_id="abc", source="claude-code",
        expected_prev_round_id=None,
        rounds=[_round("r1", "one")],
        created_at="2026-05-20T00:00:00Z",
        metadata={"cwd": "/work"},
    ))
    res = await app.state.ingest.append_rounds(AppendRoundsRequest(
        session_id="abc", source="claude-code",
        expected_prev_round_id="r1",
        rounds=[],
        created_at="2026-05-20T00:00:00Z",
        metadata={"cwd": "/work"},
    ))
    assert res.status == "ok"
    assert res.appended_count == 0
    assert res.new_last_round_id == "r1"
    assert res.round_count == 1

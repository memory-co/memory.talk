"""IndexWriteBuffer behavior + threshold / lifecycle / failure paths.

The integration paths (ingest + backfill going through the buffer) are
covered indirectly by the existing test_search / test_backfill suites
running against ``flush_rows=1``. These tests focus on the buffer's
own contract: threshold flush, time-based flush, end-of-life drain,
flush-failure handling, observability fields.
"""
from __future__ import annotations
import asyncio

import pytest

from memorytalk.service.index_buffer import IndexWriteBuffer


pytestmark = pytest.mark.asyncio


def _round_row(sid: str, idx: int):
    return {
        "session_id": sid, "idx": idx, "role": "human",
        "text": "hello", "vector": [0.0] * 384,
    }


# ────────── threshold flush ──────────

async def test_add_below_threshold_does_not_flush(app):
    buf = IndexWriteBuffer(
        vectors=app.state.vectors, db=app.state.db,
        flush_rows=10, flush_interval_seconds=0,
    )
    await buf.add_rounds("sess-x", [_round_row("sess-x", 1), _round_row("sess-x", 2)])
    assert buf.pending_rows == 2
    assert buf.flush_count == 0


async def test_add_at_threshold_triggers_flush(app):
    buf = IndexWriteBuffer(
        vectors=app.state.vectors, db=app.state.db,
        flush_rows=3, flush_interval_seconds=0,
    )
    await buf.add_rounds(
        "sess-x", [_round_row("sess-x", i) for i in range(3)],
    )
    # Threshold met → synchronous flush before add returns.
    assert buf.pending_rows == 0
    assert buf.flush_count == 1
    assert buf.last_flush_rows == 3


async def test_explicit_flush_drains_partial_buffer(app):
    buf = IndexWriteBuffer(
        vectors=app.state.vectors, db=app.state.db,
        flush_rows=100, flush_interval_seconds=0,
    )
    await buf.add_rounds("sess-x", [_round_row("sess-x", 1)])
    assert buf.pending_rows == 1
    n = await buf.flush()
    assert n == 1
    assert buf.pending_rows == 0


# ────────── bump_indexed_count happens on flush, not on add ──────────

async def test_indexed_count_updates_only_after_flush(app, client):
    """The session's indexed_round_count must reflect what LanceDB
    actually contains — not what's just sitting in the buffer."""
    # Seed a session via the API so the sessions row exists.
    r = await client.post("/v3/sessions/ensure", json={
        "session_id": "sess-test-x", "source": "claude-code",
    })
    r.raise_for_status()
    await client.post("/v3/sessions/append", json={
        "session_id": "sess-test-x", "source": "claude-code",
        "expected_prev_round_id": None,
        "rounds": [{
            "round_id": "r1", "role": "human",
            "content": [{"type": "text", "text": "hi"}],
        }],
        "created_at": "2026-05-29T00:00:00Z", "metadata": {"cwd": "/work"},
    })

    # Use a dedicated buffer with a large threshold so adds don't auto-flush.
    buf = IndexWriteBuffer(
        vectors=app.state.vectors, db=app.state.db,
        flush_rows=100, flush_interval_seconds=0,
    )
    sid = "sess-test-x"
    row = await app.state.db.sessions.get(sid)
    indexed_before = row["indexed_round_count"]
    await buf.add_rounds(sid, [_round_row(sid, 10)])
    # No flush yet → counter unchanged.
    row = await app.state.db.sessions.get(sid)
    assert row["indexed_round_count"] == indexed_before
    # Flush → counter moves.
    await buf.flush()
    row = await app.state.db.sessions.get(sid)
    assert row["indexed_round_count"] == indexed_before + 1


# ────────── failure path ──────────

async def test_flush_failure_records_error_drops_rows(app, monkeypatch):
    """Buffer is intentionally lossy on flush failure — the
    IndexBackfill loop is the recovery path, NOT in-buffer retry.
    Otherwise a persistently failing endpoint grows the queue without
    bound."""
    buf = IndexWriteBuffer(
        vectors=app.state.vectors, db=app.state.db,
        flush_rows=100, flush_interval_seconds=0,
    )

    async def boom(rows):
        raise RuntimeError("lance broke")

    monkeypatch.setattr(app.state.vectors, "add_rounds", boom)
    await buf.add_rounds("sess-x", [_round_row("sess-x", 1)])
    n = await buf.flush()
    assert n == 0
    assert "lance broke" in (buf.last_flush_error or "")
    assert buf.pending_rows == 0  # dropped, not re-queued


# ────────── time-based flush ──────────

async def test_background_flusher_drains_on_interval(app):
    buf = IndexWriteBuffer(
        vectors=app.state.vectors, db=app.state.db,
        flush_rows=10_000, flush_interval_seconds=0.05,
    )
    buf.start()
    try:
        await buf.add_rounds("sess-x", [_round_row("sess-x", 1)])
        # Wait long enough for the background tick to fire at least
        # once after the add.
        for _ in range(30):
            await asyncio.sleep(0.05)
            if buf.flush_count > 0:
                break
        assert buf.flush_count >= 1, "background flusher never fired"
    finally:
        await buf.stop()


async def test_stop_performs_final_flush(app):
    buf = IndexWriteBuffer(
        vectors=app.state.vectors, db=app.state.db,
        flush_rows=10_000, flush_interval_seconds=0,
    )
    await buf.add_rounds("sess-x", [_round_row("sess-x", 1)])
    assert buf.pending_rows == 1
    await buf.stop()
    # Stop must drain — shutdown otherwise loses queued vectors.
    assert buf.pending_rows == 0


# ────────── disabled-vectors safety ──────────

async def test_noop_when_vectors_is_none(data_root, monkeypatch):
    """A boot without a LanceDB backend still has a buffer (lifespan
    constructs one unconditionally) — it must accept calls + flush
    without raising so the disabled-vectors path stays graceful."""
    buf = IndexWriteBuffer(vectors=None, db=None, flush_rows=1)
    await buf.add_rounds("sess-x", [_round_row("sess-x", 1)])
    assert buf.pending_rows == 0  # add_rounds was a no-op
    assert await buf.flush() == 0

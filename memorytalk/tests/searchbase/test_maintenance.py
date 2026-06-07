"""Maintenance — searchbase self-management subsystem.

These tests pin the contract that ``Maintenance`` owns:

  1. Periodic compaction loop (run-at-start + tick).
  2. Crash-safety — a single failing iteration must NOT terminate the
     loop. This is the regression net for the design gap that motivated
     pulling maintenance out of ``backend.py`` into its own class.
  3. EMFILE recovery (lock + generation counter + connection reset).
  4. ``health()`` returns the canonical six-field dict (single source
     of truth for ``LocalSearchBackend.health().detail``).

Tests construct Maintenance directly against a real CollectionIndex so
the contract is checked against actual LanceDB behavior, not a mock.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from memorytalk.searchbase.local.index import CollectionIndex
from memorytalk.searchbase.local.maintenance import Maintenance


@pytest.fixture
async def index(data_root):
    """A real CollectionIndex with one declared collection — minimal
    enough for maintenance-level assertions but real enough that
    compaction actually runs against LanceDB."""
    data_dir = Path(data_root) / "v_main_test"
    idx = await CollectionIndex.create(
        data_dir, dim=4, collections={"things": {"fields": {}}},
    )
    yield idx
    try:
        await idx.db.close()
    except Exception:
        pass


# ────────── lifecycle ──────────

async def test_start_then_stop_is_clean(index):
    m = Maintenance(index, compact_interval_seconds=10.0)
    await m.start()
    assert m._loop_task is not None
    await m.stop()
    assert m._loop_task is None


async def test_start_is_idempotent(index):
    m = Maintenance(index, compact_interval_seconds=10.0)
    await m.start()
    first = m._loop_task
    await m.start()
    assert m._loop_task is first  # didn't spawn a second one
    await m.stop()


async def test_stop_without_start_is_safe(index):
    m = Maintenance(index, compact_interval_seconds=10.0)
    await m.stop()  # no raise


# ────────── periodic compaction ──────────

async def test_loop_compacts_at_start_and_on_interval(index):
    m = Maintenance(index, compact_interval_seconds=0.05)
    await m.start()
    try:
        # Wait long enough for the startup compaction + several ticks.
        await asyncio.sleep(0.3)
        assert m.compactions >= 2  # startup (1) + ≥1 periodic tick
        assert m.last_compact_at_iso is not None
    finally:
        await m.stop()


async def test_loop_survives_iteration_exception(index, monkeypatch):
    """The whole point of moving maintenance into its own class was so a
    single failing iteration logs + continues instead of silently
    killing the loop. Pin that property."""
    m = Maintenance(index, compact_interval_seconds=0.05)

    call_count = {"n": 0}
    original = index.optimize

    async def flaky(collection):
        call_count["n"] += 1
        if call_count["n"] == 2:
            # Second invocation raises; loop must keep going.
            raise RuntimeError("synthetic compact failure")
        return await original(collection)

    monkeypatch.setattr(index, "optimize", flaky)

    await m.start()
    try:
        # Long enough for at least the startup compact + the failing
        # iteration + a recovery iteration.
        await asyncio.sleep(0.3)
        # Three is the minimum to assert: startup (succeeds), tick
        # (raises), next tick (succeeds again — proves the loop lived
        # through the exception).
        assert call_count["n"] >= 3
        # And the loop is still alive.
        assert m._loop_task is not None and not m._loop_task.done()
    finally:
        await m.stop()


async def test_compact_all_clears_error_on_full_success(index, monkeypatch):
    m = Maintenance(index, compact_interval_seconds=10.0)

    # First pass: a synthetic failure → error recorded.
    async def boom(collection):
        raise RuntimeError("bad")

    monkeypatch.setattr(index, "optimize", boom)
    await m.compact_all()
    assert m.last_compact_error and "bad" in m.last_compact_error

    # Restore healthy behavior → next pass clears the error field.
    monkeypatch.undo()
    await m.compact_all()
    assert m.last_compact_error is None


# ────────── EMFILE recovery ──────────

async def test_recover_from_emfile_advances_counter(index):
    m = Maintenance(index, compact_interval_seconds=10.0)
    index.attach_maintenance(m)
    before = m.emfile_recoveries
    await m.recover_from_emfile()
    assert m.emfile_recoveries == before + 1
    assert m.last_emfile_at_iso is not None


async def test_recover_from_emfile_concurrent_callers_share_work(index):
    """Two concurrent recoveries must net out to exactly one cycle —
    the generation counter is what protects us from N concurrent
    EMFILEs spinning N redundant reconnects."""
    m = Maintenance(index, compact_interval_seconds=10.0)
    index.attach_maintenance(m)
    before = m.emfile_recoveries
    await asyncio.gather(
        m.recover_from_emfile(),
        m.recover_from_emfile(),
    )
    assert m.emfile_recoveries == before + 1


async def test_recover_from_emfile_reconnects_lancedb(index):
    """The reconnect is what actually frees the held reader fds —
    after recovery the connection object must be a fresh one."""
    m = Maintenance(index, compact_interval_seconds=10.0)
    index.attach_maintenance(m)
    db_before = index.db
    await m.recover_from_emfile()
    assert index.db is not db_before


# ────────── observability ──────────

async def test_health_returns_all_six_fields(index):
    m = Maintenance(index, compact_interval_seconds=10.0)
    h = m.health()
    for key in (
        "compactions", "last_compact_at_iso", "last_compact_error",
        "emfile_recoveries", "last_emfile_at_iso", "last_recovery_error",
    ):
        assert key in h, f"missing {key} in health() output: {h}"


async def test_health_reflects_state_after_operations(index):
    m = Maintenance(index, compact_interval_seconds=10.0)
    await m.compact_all()
    h = m.health()
    assert h["compactions"] == 1
    assert h["last_compact_at_iso"] is not None
    assert h["last_compact_error"] is None

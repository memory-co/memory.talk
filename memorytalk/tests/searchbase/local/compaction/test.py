"""compaction — Maintenance 生命周期 + 周期循环 + 崩溃韧性 + health
观察. See README.md.
"""
from __future__ import annotations

import asyncio

import pytest

from memorytalk.config import Config
from memorytalk.provider.embedding import get_embedder
from memorytalk.searchbase import LocalSearchBackend
from memorytalk.searchbase.local.maintenance import Maintenance


# ────────── lifecycle: start / stop / idempotency ──────────

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


# ────────── periodic loop ──────────

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


async def test_maintenance_loop_compacts_via_backend_health(data_root):
    """Same property as the test above but driven through the
    ``backend.health()`` surface — locks down the contract that the
    counter is reachable from the public API, not just the private
    ``_maintenance.compactions`` attribute."""
    config = Config(data_root)
    config.ensure_dirs()
    b = await LocalSearchBackend.create(
        name="v1", data_dir=config.vectors_dir,
        dim=config.settings.embedding.dim, embedder=get_embedder(config),
        collections={"cards": {"fields": {}}},
        compact_interval_seconds=0.05,
    )
    try:
        await asyncio.sleep(0.3)
        health = await b.health()
        assert health.detail["compactions"] >= 2
    finally:
        await b.close()


# ────────── crash-safety: one failing iteration must NOT kill the loop ──────────

async def test_loop_survives_iteration_exception(index, monkeypatch):
    """Regression net for the design gap that prompted lifting
    Maintenance into its own class: a single iteration's failure used
    to silently terminate the loop until the next process restart.
    Now each iteration is wrapped in its own try/except."""
    m = Maintenance(index, compact_interval_seconds=0.05)

    call_count = {"n": 0}
    original = index.optimize

    async def flaky(collection):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("synthetic compact failure")
        return await original(collection)

    monkeypatch.setattr(index, "optimize", flaky)

    await m.start()
    try:
        # Long enough for: startup compact (1) + failing iteration (2)
        # + recovery iteration (3+).
        await asyncio.sleep(0.3)
        assert call_count["n"] >= 3
        assert m._loop_task is not None and not m._loop_task.done()
    finally:
        await m.stop()


# ────────── error field latches latest, not historical ──────────

async def test_compact_all_clears_error_on_full_success(index, monkeypatch):
    m = Maintenance(index, compact_interval_seconds=10.0)

    # Pass 1: synthetic failure → error recorded.
    async def boom(collection):
        raise RuntimeError("bad")

    monkeypatch.setattr(index, "optimize", boom)
    await m.compact_all()
    assert m.last_compact_error and "bad" in m.last_compact_error

    # Pass 2: restore healthy behavior → error clears.
    monkeypatch.undo()
    await m.compact_all()
    assert m.last_compact_error is None


# ────────── health: surface + state reflection ──────────

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


async def test_backend_health_exposes_emfile_counters(backend):
    """``backend.health().detail`` is the public read surface — it must
    surface the index's recovery counters, not drop them."""
    health = await backend.health()
    assert "emfile_recoveries" in health.detail

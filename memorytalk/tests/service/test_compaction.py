"""LanceDB compaction: optimize() + IndexBackfill wiring.

Background: the append-only ingest path leaks one fragment per embedder
batch; with no vector ANN index, search flat-scans every fragment and
eventually hits EMFILE. Compaction (LanceDB's optimize) merges fragments
+ prunes old versions. These tests pin the new surface:

  - LanceStore.optimize: no-op on a missing table, runs on a populated one
  - IndexBackfill.compact_once: optimizes both tables, gated on vectors
  - trigger_startup_compaction: fires a one-shot, no-op without vectors
  - lifespan: a boot always schedules the startup compaction
"""
from __future__ import annotations
import pytest

from memorytalk.service.backfill import IndexBackfill


pytestmark = pytest.mark.asyncio


def _round_row(idx: int):
    return {
        "session_id": "sess-x", "idx": idx, "role": "human",
        "text": "hello world", "vector": [0.0] * 384,
    }


# ────────── LanceStore.optimize ──────────

async def test_optimize_missing_table_is_noop(app):
    """Fresh data root → rounds table not created yet → skipped, no raise."""
    v = app.state.vectors
    assert v is not None
    res = await v.optimize(v.ROUNDS)
    assert res["skipped"] == "missing"
    assert res["table"] == v.ROUNDS


async def test_optimize_runs_on_populated_table(app):
    v = app.state.vectors
    await v.add_rounds([_round_row(1), _round_row(2)])
    res = await v.optimize(v.ROUNDS)
    assert res["table"] == v.ROUNDS
    assert "stats" in res
    # Table stays usable after compaction — rows are still there.
    table = await v.db.open_table(v.ROUNDS)
    assert await table.count_rows() == 2


async def test_optimize_prunes_old_versions(app):
    """cleanup_older_than=0 → all versions but latest pruned. After
    several appends + an optimize, the version count collapses."""
    v = app.state.vectors
    for i in range(5):
        await v.add_rounds([_round_row(i)])  # 5 appends → 5+ versions
    table = await v.db.open_table(v.ROUNDS)
    versions_before = len(await table.list_versions())
    await v.optimize(v.ROUNDS)
    table = await v.db.open_table(v.ROUNDS)
    versions_after = len(await table.list_versions())
    assert versions_after < versions_before


# ────────── IndexBackfill.compact_once ──────────

async def test_compact_once_optimizes_both_tables(app, monkeypatch):
    v = app.state.vectors
    await v.add_rounds([_round_row(1)])
    called: list[str] = []
    orig = v.optimize

    async def spy(table_name):
        called.append(table_name)
        return await orig(table_name)

    monkeypatch.setattr(v, "optimize", spy)
    bf = IndexBackfill(db=app.state.db, vectors=v, embedder=app.state.embedder)
    await bf._compact_once()
    assert v.ROUNDS in called
    assert v.CARDS in called


async def test_compact_once_noop_without_vectors(app):
    bf = IndexBackfill(db=app.state.db, vectors=None, embedder=None)
    # Must not raise — compaction is best-effort maintenance.
    await bf._compact_once()


async def test_compact_once_swallows_optimize_errors(app, monkeypatch):
    """A compaction failure (e.g. EMFILE on a degenerate table) must
    never propagate — it gets logged + recorded, the server lives on."""
    v = app.state.vectors

    async def boom(table_name):
        raise OSError("Too many open files")

    monkeypatch.setattr(v, "optimize", boom)
    bf = IndexBackfill(db=app.state.db, vectors=v, embedder=app.state.embedder)
    await bf._compact_once()  # no raise
    assert bf.last_error is not None
    assert "compact" in bf.last_error


# ────────── trigger_startup_compaction ──────────

async def test_trigger_startup_compaction_fires_task(app):
    v = app.state.vectors
    await v.add_rounds([_round_row(1)])
    bf = IndexBackfill(db=app.state.db, vectors=v, embedder=app.state.embedder)
    bf.trigger_startup_compaction()
    assert bf._compact_task is not None
    # Let it finish cleanly.
    await bf._compact_task


async def test_trigger_startup_compaction_noop_without_vectors(app):
    bf = IndexBackfill(db=app.state.db, vectors=None, embedder=None)
    bf.trigger_startup_compaction()
    assert bf._compact_task is None


# ────────── lifespan integration ──────────

async def test_lifespan_schedules_startup_compaction(app):
    """The app fixture boots through the real lifespan; the startup
    compaction task must have been created (gated on vectors, which the
    dummy-embedder test config has)."""
    bf = app.state.backfill
    assert bf is not None
    # Task exists (may already be done — we only assert it was scheduled).
    assert bf._compact_task is not None

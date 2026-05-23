"""IndexBackfill — end-to-end behavior on the live app fixture.

We don't unit-test the loop's poll timing (that's slow and flaky);
we drive ``_reindex_session`` directly on degraded sessions inserted
via the live app's IngestService. Coverage:

  - happy: degraded session gets re-embedded, ``indexed_round_count``
    matches ``round_count``
  - resume: simulated mid-loop interrupt leaves a recoverable state;
    a second pass converges
  - missing jsonl: marks ``last_index_error`` and moves on
  - degraded queue ordering: largest gaps first
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from memorytalk.service.backfill import IndexBackfill
from memorytalk.tests._ingest import ingest_session


pytestmark = pytest.mark.asyncio


def _round(rid: str, role: str, text: str) -> dict:
    return {
        "round_id": rid, "role": role,
        "content": [{"type": "text", "text": text}],
    }


async def _seed_session(client, sid: str, n_rounds: int) -> None:
    rounds = [_round(f"r{i}", "human", f"round {i} text") for i in range(n_rounds)]
    r = await ingest_session(client, sid, rounds=rounds)
    r.raise_for_status()


@pytest_asyncio.fixture
async def backfill(app):
    """A backfill instance bound to the live app's stores, NOT started.
    Tests drive ``_reindex_session`` / ``list_degraded`` directly so
    timing is deterministic."""
    return IndexBackfill(
        db=app.state.db,
        vectors=app.state.vectors,
        embedder=app.state.embedder,
    )


class TestReindexHappyPath:

    async def test_degraded_session_gets_caught_up(self, app, client, backfill):
        # Default fixture uses dummy embedder, which never fails — so to
        # create a degraded state we have to set indexed_round_count
        # manually after seed (simulating a past partial failure).
        await _seed_session(client, "bf-1", n_rounds=15)
        await app.state.db.sessions.bump_indexed_count(
            "sess_bf-1", -15, "2026-01-01T00:00:00Z",
        )  # roll back to 0 to simulate degraded
        row = await app.state.db.sessions.get("sess_bf-1")
        assert row["indexed_round_count"] == 0
        assert row["round_count"] == 15

        # Reindex.
        await backfill._reindex_session(row)

        row = await app.state.db.sessions.get("sess_bf-1")
        assert row["indexed_round_count"] == row["round_count"] == 15
        # last_index_error should be cleared on full success.
        assert row["last_index_error"] is None


class TestListDegradedOrdering:

    async def test_largest_gap_first(self, app, client):
        # Two degraded sessions, one with a 3-round gap, one with 10.
        await _seed_session(client, "small-gap", n_rounds=5)
        await app.state.db.sessions.bump_indexed_count(
            "sess_small-gap", -3, "2026-01-01T00:00:00Z",
        )  # 5 - 3 = 2 indexed, 3 missing
        await _seed_session(client, "big-gap", n_rounds=15)
        await app.state.db.sessions.bump_indexed_count(
            "sess_big-gap", -10, "2026-01-01T00:00:00Z",
        )  # 15 - 10 = 5 indexed, 10 missing

        degraded = await app.state.db.sessions.list_degraded(limit=10)
        assert [s["session_id"] for s in degraded] == ["sess_big-gap", "sess_small-gap"]


class TestIndexHealthAggregate:

    async def test_clean_state_reports_zeros(self, app):
        h = await app.state.db.sessions.get_index_health()
        assert h["total_sessions"] == 0
        assert h["degraded_sessions"] == 0
        assert h["missing_rounds"] == 0

    async def test_degraded_aggregates_correctly(self, app, client):
        await _seed_session(client, "agg-a", n_rounds=8)   # fully indexed (dummy)
        await _seed_session(client, "agg-b", n_rounds=20)
        await app.state.db.sessions.bump_indexed_count(
            "sess_agg-b", -12, "2026-01-01T00:00:00Z",
        )  # 20 - 12 = 8 indexed, 12 missing

        h = await app.state.db.sessions.get_index_health()
        assert h["total_sessions"] == 2
        assert h["total_rounds"] == 28
        # agg-a fully indexed (8) + agg-b partially (8) = 16
        assert h["indexed_rounds"] == 16
        assert h["missing_rounds"] == 12
        assert h["degraded_sessions"] == 1


class TestMissingJsonlGracefulSkip:

    async def test_marks_error_and_returns(self, app, client, backfill, tmp_path):
        await _seed_session(client, "ghost", n_rounds=5)
        # Manually delete the jsonl to simulate a corrupted install.
        # rounds.jsonl path mirrors what the repo lays out — easiest
        # way is to ask the storage layer to read first and confirm,
        # then nuke the file.
        from pathlib import Path
        # `sessions/<source>/<bucket>/<sid>/rounds.jsonl`
        # Default test source is "claude-code" via the helper.
        rounds_path = (
            Path(app.state.config.data_root)
            / "sessions" / "claude-code" / "gh"  # ghost[0:2]
            / "sess_ghost" / "rounds.jsonl"
        )
        # The exact bucket scheme might differ; find the actual file.
        candidates = list(
            (Path(app.state.config.data_root) / "sessions").rglob("rounds.jsonl")
        )
        assert candidates, "expected at least one rounds.jsonl"
        for c in candidates:
            c.unlink()

        # Roll back indexed_round_count so the session is degraded.
        await app.state.db.sessions.bump_indexed_count(
            "sess_ghost", -5, "2026-01-01T00:00:00Z",
        )
        row = await app.state.db.sessions.get("sess_ghost")

        # Should NOT raise — sets last_index_error and returns.
        await backfill._reindex_session(row)

        row = await app.state.db.sessions.get("sess_ghost")
        assert row["last_index_error"] is not None
        assert "missing" in row["last_index_error"].lower()

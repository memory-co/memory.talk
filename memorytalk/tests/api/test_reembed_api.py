"""POST /v4/searchbase/reembed + GET /v4/status reembedding surface.

Drives the endpoint through the live app (dummy embedder, dim=384 from
the ``data_root`` fixture). Covers the contract's status codes, the
dry_run probe, the happy-path run, the in-progress guard, per-object
failure isolation, and the status flip to ``reembedding``.
"""
from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.asyncio


async def _seed(client) -> str:
    """One card (issue → cards collection) + one position (claim →
    positions collection) so a reembed has rows to rebuild."""
    r = await client.post("/v4/cards", json={"issue": "Which vector db?"})
    assert r.status_code == 200, r.text
    card_id = r.json()["card_id"]
    # A position needs a real session for its --source provenance.
    from memorytalk.tests._ingest import ingest_session
    rounds = [{"round_id": "r1", "role": "human",
               "content": [{"type": "text", "text": "talk about lancedb"}]}]
    sr = await ingest_session(client, "reembed-src", rounds=rounds)
    sr.raise_for_status()
    sid = sr.json()["session_id"]
    pr = await client.post(
        f"/v4/cards/{card_id}/positions",
        json={"claim": "Use LanceDB", "source": {"session_id": sid, "indexes": "1"}},
    )
    assert pr.status_code == 200, pr.text
    return card_id


# ────────── error status codes ──────────

async def test_missing_expected_dim_400(client):
    r = await client.post("/v4/searchbase/reembed", json={})
    assert r.status_code == 400
    assert "expected_dim" in r.text


async def test_dim_mismatch_400(client):
    r = await client.post("/v4/searchbase/reembed", json={"expected_dim": 999})
    assert r.status_code == 400
    body = r.json()
    assert "dim mismatch" in body["detail"]
    assert "expected 999" in body["detail"]
    assert "settings has 384" in body["detail"]


# ────────── dry_run probes without mutating ──────────

async def test_dry_run_reports_counts_without_running(client):
    await _seed(client)
    r = await client.post(
        "/v4/searchbase/reembed", json={"expected_dim": 384, "dry_run": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "dry_run"
    assert body["expected_dim"] == 384
    assert body["current_dim"] == 384
    # one card + one position were indexed.
    assert body["cards_total"] >= 2
    # vectors are indexed at the configured dim already (no dim change).
    assert body["vector_index_dim"] == 384
    # dry_run must not flip status.
    s = await client.get("/v4/status")
    assert s.json()["status"] == "running"


# ────────── happy path actual run ──────────

async def test_run_reembeds_and_reports(client):
    await _seed(client)
    r = await client.post("/v4/searchbase/reembed", json={"expected_dim": 384})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["cards_processed"] >= 2
    assert body["cards_failed"] == 0
    assert "duration_seconds" in body
    # guard released → a second run is allowed.
    again = await client.post("/v4/searchbase/reembed", json={"expected_dim": 384})
    assert again.status_code == 200


# ────────── in-progress guard ──────────

async def test_in_progress_guard_409(client, app):
    # Hold the guard as if a run were active, then a fresh request 409s.
    app.state.reembed._running = True
    try:
        r = await client.post("/v4/searchbase/reembed", json={"expected_dim": 384})
        assert r.status_code == 409
        assert "already in progress" in r.json()["detail"]
    finally:
        app.state.reembed._running = False


# ────────── status flips to reembedding mid-run ──────────

async def test_status_reembedding_mid_run(client, app):
    # Simulate a run in flight: status must report ``reembedding`` + the
    # processed-so-far counter (the live progress surface).
    app.state.reembed._running = True
    app.state.reembed._processed = 7
    try:
        s = await client.get("/v4/status")
        body = s.json()
        assert body["status"] == "reembedding"
        assert body["reembed_processed"] == 7
    finally:
        app.state.reembed._running = False
        app.state.reembed._processed = 0
    # back to normal once the run ends.
    s2 = await client.get("/v4/status")
    assert s2.json()["status"] == "running"
    assert s2.json()["reembed_processed"] is None


# ────────── per-object failure increments cards_failed without aborting ──────────

async def test_per_object_failure_counts_without_abort(client, app):
    await _seed(client)

    real_embed = app.state.searchbase._embedder.embed
    calls = {"n": 0}

    async def flaky(texts):
        # Fail exactly the first re-embed call; succeed for the rest. A
        # plain Exception (not ConnectionError) → isolated, run continues.
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("boom")
        return await real_embed(texts)

    app.state.searchbase._embedder.embed = flaky
    try:
        r = await client.post("/v4/searchbase/reembed", json={"expected_dim": 384})
    finally:
        app.state.searchbase._embedder.embed = real_embed
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["cards_failed"] == 1
    assert body["cards_processed"] >= 1


# ────────── concurrent real runs: the guard serializes ──────────

async def test_concurrent_runs_one_409s(client, app):
    await _seed(client)

    # Make embed slow enough that the two requests overlap.
    real_embed = app.state.searchbase._embedder.embed

    async def slow(texts):
        await asyncio.sleep(0.05)
        return await real_embed(texts)

    app.state.searchbase._embedder.embed = slow
    try:
        r1, r2 = await asyncio.gather(
            client.post("/v4/searchbase/reembed", json={"expected_dim": 384}),
            client.post("/v4/searchbase/reembed", json={"expected_dim": 384}),
            return_exceptions=True,
        )
    finally:
        app.state.searchbase._embedder.embed = real_embed
    codes = sorted(x.status_code for x in (r1, r2))
    # one succeeds (200), the other hits the in-progress guard (409).
    assert codes == [200, 409]

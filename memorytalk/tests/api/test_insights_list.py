"""GET /v4/insights — read-only structural list (tag / since / until).

Insight is read-only in v4 (the old v3 card, data preserved). These tests
seed insights directly via SQL (no create endpoint) and pin what the
read-only list covers: tag operator variety + time window +
total-vs-returned + payload shape (``insight_id`` surface).
"""
from __future__ import annotations
import json as _json

import pytest


pytestmark = pytest.mark.asyncio

_SEQ = {"n": 0}


async def _seed_insight(app, insight: str, *, tags: dict | None = None) -> str:
    """Insert one read-only insight row directly. Returns the insight_id."""
    _SEQ["n"] += 1
    iid = f"insight_seed{_SEQ['n']:04d}"
    db = app.state.db
    now = "2026-01-01T00:00:00Z"
    await db.conn.execute(
        "INSERT INTO insights (card_id, insight, rounds, tags, created_at) "
        "VALUES (?, ?, '[]', ?, ?)",
        (iid, insight, _json.dumps(tags or {}), now),
    )
    await db.conn.execute(
        "INSERT INTO insight_stats "
        "(card_id, review_up, review_down, review_neutral, review_count, "
        " read_count, updated_at) VALUES (?, 0, 0, 0, 0, 0, ?)",
        (iid, now),
    )
    await db.conn.commit()
    return iid


async def _set_created_at(app, iid: str, iso: str) -> None:
    await app.state.db.conn.execute(
        "UPDATE insights SET created_at = ? WHERE card_id = ?", (iso, iid),
    )
    await app.state.db.conn.commit()


# ────────── empty + basic ──────────

async def test_empty_db_returns_zero(client):
    r = await client.get("/v4/insights")
    assert r.status_code == 200
    assert r.json() == {"total": 0, "returned": 0, "cards": []}


async def test_lists_existing_insights(app, client):
    a = await _seed_insight(app, "first insight")
    b = await _seed_insight(app, "second insight")
    body = (await client.get("/v4/insights")).json()
    assert body["total"] == 2
    assert {c["insight_id"] for c in body["cards"]} == {a, b}


# ────────── pagination ──────────

async def test_limit_caps_returned_not_total(app, client):
    for i in range(4):
        await _seed_insight(app, f"insight {i}")
    r = await client.get("/v4/insights", params={"limit": 2})
    body = r.json()
    assert body["total"] == 4
    assert body["returned"] == 2
    assert len(body["cards"]) == 2


# ────────── filter: tag (all 5 operators) ──────────

async def test_filter_tag_equality(app, client):
    a = await _seed_insight(app, "billable",
                            tags={"project": "billing", "status": "wip"})
    await _seed_insight(app, "infra-y", tags={"project": "infra"})
    r = await client.get("/v4/insights", params={"tag": "project=billing"})
    body = r.json()
    assert body["total"] == 1
    assert body["cards"][0]["insight_id"] == a


async def test_filter_tag_presence(app, client):
    a = await _seed_insight(app, "has-tag", tags={"project": "x"})
    await _seed_insight(app, "no-tag")
    r = await client.get("/v4/insights", params={"tag": "project"})
    body = r.json()
    assert {c["insight_id"] for c in body["cards"]} == {a}


async def test_filter_tag_ne_excludes_null(app, client):
    a = await _seed_insight(app, "wip", tags={"status": "wip"})
    await _seed_insight(app, "draft", tags={"status": "draft"})
    await _seed_insight(app, "untagged")
    r = await client.get("/v4/insights", params={"tag": "status!=draft"})
    body = r.json()
    assert {x["insight_id"] for x in body["cards"]} == {a}


async def test_filter_tag_in_list(app, client):
    a = await _seed_insight(app, "wip", tags={"status": "wip"})
    b = await _seed_insight(app, "rev", tags={"status": "review"})
    await _seed_insight(app, "done", tags={"status": "done"})
    r = await client.get("/v4/insights", params={"tag": "status=wip,review"})
    body = r.json()
    assert {x["insight_id"] for x in body["cards"]} == {a, b}


async def test_filter_tag_absent(app, client):
    await _seed_insight(app, "tagged", tags={"project": "x"})
    b = await _seed_insight(app, "untagged")
    r = await client.get("/v4/insights", params={"tag": "!project"})
    body = r.json()
    assert {x["insight_id"] for x in body["cards"]} == {b}


# ────────── filter: since / until ──────────

async def test_filter_since_until(client, app):
    a = await _seed_insight(app, "older")
    b = await _seed_insight(app, "newer")
    await _set_created_at(app, a, "2026-04-01T00:00:00Z")
    await _set_created_at(app, b, "2026-05-15T00:00:00Z")

    r = await client.get("/v4/insights", params={"since": "2026-05-01T00:00:00Z"})
    assert r.json()["total"] == 1
    assert r.json()["cards"][0]["insight_id"] == b


async def test_invalid_iso_rejected(client):
    r = await client.get("/v4/insights", params={"since": "yesterday"})
    assert r.status_code == 400


# ────────── response shape ──────────

async def test_response_carries_stats_and_tags(app, client):
    iid = await _seed_insight(app, "test", tags={"x": "1"})
    body = (await client.get("/v4/insights")).json()
    row = body["cards"][0]
    assert row["insight_id"] == iid
    assert row["insight"] == "test"
    assert row["tags"] == {"x": "1"}
    assert row["stats"]["review_up"] == 0
    assert row["stats"]["read_count"] == 0
    assert "rounds" not in row

"""GET /v4/insights — structural list (tag / since / until).

Stats filters live on ``search "" -w 'DSL'`` (intentionally NOT
duplicated here); these tests pin what list DOES cover: tag operator
variety + time window + total-vs-returned + payload shape.
"""
from __future__ import annotations
import pytest

from memorytalk.tests._ingest import ingest_session


pytestmark = pytest.mark.asyncio


async def _seed_session(client) -> str:
    """Cards reference real session rounds; ingest one we can point at."""
    r = await ingest_session(client, "cl-base", rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hi"}]},
        {"round_id": "r2", "role": "assistant",
         "content": [{"type": "text", "text": "hello"}]},
    ])
    r.raise_for_status()
    return r.json()["session_id"]


async def _create_card(client, sid: str, insight: str, *, tags: dict | None = None) -> str:
    body = {"insight": insight,
            "rounds": [{"session_id": sid, "indexes": "1-2"}]}
    if tags is not None:
        body["tags"] = tags
    r = await client.post("/v4/insights", json=body)
    r.raise_for_status()
    return r.json()["card_id"]


async def _set_created_at(app, cid: str, iso: str) -> None:
    await app.state.db.conn.execute(
        "UPDATE insights SET created_at = ? WHERE card_id = ?", (iso, cid),
    )
    await app.state.db.conn.commit()


# ────────── empty + basic ──────────

async def test_empty_db_returns_zero(client):
    r = await client.get("/v4/insights")
    assert r.status_code == 200
    assert r.json() == {"total": 0, "returned": 0, "cards": []}


async def test_lists_existing_cards(client):
    sid = await _seed_session(client)
    a = await _create_card(client, sid, "first insight")
    b = await _create_card(client, sid, "second insight")
    body = (await client.get("/v4/insights")).json()
    assert body["total"] == 2
    assert {c["card_id"] for c in body["cards"]} == {a, b}


# ────────── pagination ──────────

async def test_limit_caps_returned_not_total(client):
    sid = await _seed_session(client)
    for i in range(4):
        await _create_card(client, sid, f"insight {i}")
    r = await client.get("/v4/insights", params={"limit": 2})
    body = r.json()
    assert body["total"] == 4
    assert body["returned"] == 2
    assert len(body["cards"]) == 2


# ────────── filter: tag (all 5 operators) ──────────

async def test_filter_tag_equality(client):
    sid = await _seed_session(client)
    a = await _create_card(client, sid, "billable",
                           tags={"project": "billing", "status": "wip"})
    b = await _create_card(client, sid, "infra-y", tags={"project": "infra"})
    r = await client.get("/v4/insights", params={"tag": "project=billing"})
    body = r.json()
    assert body["total"] == 1
    assert body["cards"][0]["card_id"] == a


async def test_filter_tag_presence(client):
    sid = await _seed_session(client)
    a = await _create_card(client, sid, "has-tag", tags={"project": "x"})
    b = await _create_card(client, sid, "no-tag")
    r = await client.get("/v4/insights", params={"tag": "project"})
    body = r.json()
    assert {c["card_id"] for c in body["cards"]} == {a}


async def test_filter_tag_ne_excludes_null(client):
    sid = await _seed_session(client)
    a = await _create_card(client, sid, "wip", tags={"status": "wip"})
    b = await _create_card(client, sid, "draft", tags={"status": "draft"})
    c = await _create_card(client, sid, "untagged")
    r = await client.get("/v4/insights", params={"tag": "status!=draft"})
    body = r.json()
    # `a` matches; `b` doesn't (draft = draft); `c` doesn't (strict NE
    # excludes NULL — design choice for orthogonal operators).
    assert {x["card_id"] for x in body["cards"]} == {a}


async def test_filter_tag_in_list(client):
    sid = await _seed_session(client)
    a = await _create_card(client, sid, "wip", tags={"status": "wip"})
    b = await _create_card(client, sid, "rev", tags={"status": "review"})
    c = await _create_card(client, sid, "done", tags={"status": "done"})
    r = await client.get("/v4/insights", params={"tag": "status=wip,review"})
    body = r.json()
    assert {x["card_id"] for x in body["cards"]} == {a, b}


async def test_filter_tag_absent(client):
    sid = await _seed_session(client)
    await _create_card(client, sid, "tagged", tags={"project": "x"})
    b = await _create_card(client, sid, "untagged")
    r = await client.get("/v4/insights", params={"tag": "!project"})
    body = r.json()
    assert {x["card_id"] for x in body["cards"]} == {b}


# ────────── filter: since / until ──────────

async def test_filter_since_until(client, app):
    sid = await _seed_session(client)
    a = await _create_card(client, sid, "older")
    b = await _create_card(client, sid, "newer")
    await _set_created_at(app, a, "2026-04-01T00:00:00Z")
    await _set_created_at(app, b, "2026-05-15T00:00:00Z")

    r = await client.get("/v4/insights", params={"since": "2026-05-01T00:00:00Z"})
    assert r.json()["total"] == 1
    assert r.json()["cards"][0]["card_id"] == b


async def test_invalid_iso_rejected(client):
    r = await client.get("/v4/insights", params={"since": "yesterday"})
    assert r.status_code == 400


# ────────── response shape ──────────

async def test_response_carries_stats_and_tags(client):
    sid = await _seed_session(client)
    cid = await _create_card(client, sid, "test", tags={"x": "1"})
    body = (await client.get("/v4/insights")).json()
    row = body["cards"][0]
    assert row["card_id"] == cid
    assert row["insight"] == "test"
    assert row["tags"] == {"x": "1"}
    # stats are joined in; freshly created card = all zeros.
    assert row["stats"]["review_up"] == 0
    assert row["stats"]["read_count"] == 0
    # No rounds in list — read <cid> for content.
    assert "rounds" not in row


# ────────── create with bad tags rejects the whole thing ──────────

async def test_create_with_invalid_tags_rejected(client):
    sid = await _seed_session(client)
    # ``1bad`` violates the key regex; whole create must fail and no
    # card row should be inserted.
    r = await client.post("/v4/insights", json={
        "insight": "x", "rounds": [{"session_id": sid, "indexes": "1"}],
        "tags": {"1bad": "y"},
    })
    assert r.status_code == 400
    # And nothing landed.
    assert (await client.get("/v4/insights")).json()["total"] == 0

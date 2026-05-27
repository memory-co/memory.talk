"""GET /v3/sessions — multi-filter listing.

Covers: every filter dimension individually + the AND combination, the
``total`` vs ``returned`` distinction (matters for the CLI "showing N
of TOTAL" hint), and a couple of input-validation cases.
"""
from __future__ import annotations
import datetime as _dt
import json
import pytest

from memorytalk.tests._ingest import ingest_session


pytestmark = pytest.mark.asyncio


# ────────── helpers ──────────

def _round(rid: str, role: str = "human", text: str = "hi"):
    return {"round_id": rid, "role": role,
            "content": [{"type": "text", "text": text}]}


async def _seed(client, sid_seed: str, *, cwd: str | None = None) -> str:
    """Ingest one session, return the canonical session_id."""
    meta = {}
    if cwd is not None:
        meta["cwd"] = cwd
    r = await ingest_session(
        client, sid_seed, rounds=[_round("r1"), _round("r2")],
        metadata=meta or {"cwd": "/work/proj"},
    )
    r.raise_for_status()
    return r.json()["session_id"]


async def _set_created_at(app, sid: str, iso: str) -> None:
    """``created_at`` is taken from the ingest envelope; we don't pass
    custom ones through the helper, so for since/until tests we patch
    SQLite directly."""
    await app.state.db.conn.execute(
        "UPDATE sessions SET created_at = ? WHERE session_id = ?",
        (iso, sid),
    )
    await app.state.db.conn.commit()


# ────────── empty + basic ──────────

async def test_empty_db_returns_zero(client):
    r = await client.get("/v3/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body == {"total": 0, "returned": 0, "sessions": []}


async def test_default_lists_all(client):
    a = await _seed(client, "a-1")
    b = await _seed(client, "a-2")
    r = await client.get("/v3/sessions")
    body = r.json()
    assert body["total"] == 2
    assert body["returned"] == 2
    sids = {s["session_id"] for s in body["sessions"]}
    assert sids == {a, b}


# ────────── pagination ──────────

async def test_limit_caps_returned_not_total(client):
    for i in range(5):
        await _seed(client, f"p-{i}")
    r = await client.get("/v3/sessions", params={"limit": 2})
    body = r.json()
    assert body["total"] == 5
    assert body["returned"] == 2
    assert len(body["sessions"]) == 2


async def test_limit_out_of_range_rejected(client):
    # FastAPI uses 422 for Query(ge=, le=) violations; we accept either
    # 400 or 422 since both are "bad client input".
    r = await client.get("/v3/sessions", params={"limit": 0})
    assert r.status_code in (400, 422), r.text
    r = await client.get("/v3/sessions", params={"limit": 300})
    assert r.status_code in (400, 422), r.text


# ────────── filter: source ──────────

async def test_filter_source(client):
    await _seed(client, "src-1")
    r = await client.get("/v3/sessions", params={"source": "claude-code"})
    assert r.json()["total"] == 1
    r = await client.get("/v3/sessions", params={"source": "codex"})
    assert r.json()["total"] == 0


# ────────── filter: cwd prefix ──────────

async def test_filter_cwd_prefix(client):
    a = await _seed(client, "cwd-a", cwd="/home/user/work/billing-svc")
    b = await _seed(client, "cwd-b", cwd="/home/user/work/infra")
    r = await client.get("/v3/sessions", params={"cwd": "/home/user/work/billing"})
    body = r.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == a
    # Prefix matching the parent yields both.
    r = await client.get("/v3/sessions", params={"cwd": "/home/user/work"})
    assert r.json()["total"] == 2


async def test_filter_cwd_special_chars_escaped(client):
    """``foo_bar`` in cwd would match ``fooXbar`` if we leaked the
    underscore wildcard through to LIKE. Explicit regression test."""
    a = await _seed(client, "esc-a", cwd="/home/foo_bar/proj")
    await _seed(client, "esc-b", cwd="/home/fooXbar/proj")  # must NOT match
    r = await client.get("/v3/sessions", params={"cwd": "/home/foo_bar"})
    body = r.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == a


# ────────── filter: tag (set + present) ──────────

async def test_filter_tag_equality(client):
    a = await _seed(client, "tag-a")
    b = await _seed(client, "tag-b")
    # Set a tag on `a` only.
    r = await client.patch(
        f"/v3/sessions/{a}/tags",
        json={"set": {"project": "billing", "status": "wip"}},
    )
    r.raise_for_status()
    r = await client.get("/v3/sessions", params={"tag": "project=billing"})
    body = r.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == a


async def test_filter_tag_presence(client):
    a = await _seed(client, "pres-a")
    b = await _seed(client, "pres-b")
    await client.patch(f"/v3/sessions/{a}/tags",
                       json={"set": {"project": "billing"}})
    await client.patch(f"/v3/sessions/{b}/tags",
                       json={"set": {"status": "wip"}})
    # `?tag=project` matches a only (presence, any value).
    r = await client.get("/v3/sessions", params={"tag": "project"})
    body = r.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == a


async def test_filter_tag_anded(client):
    a = await _seed(client, "and-a")
    b = await _seed(client, "and-b")
    await client.patch(f"/v3/sessions/{a}/tags",
                       json={"set": {"project": "billing", "status": "wip"}})
    await client.patch(f"/v3/sessions/{b}/tags",
                       json={"set": {"project": "billing"}})
    # Both have project=billing, only one has status=wip → AND yields one.
    r = await client.get("/v3/sessions",
                         params=[("tag", "project=billing"), ("tag", "status=wip")])
    body = r.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == a


async def test_filter_tag_malformed_key_rejected(client):
    # Key starts with digit, fails regex.
    r = await client.get("/v3/sessions", params={"tag": "1bad=x"})
    assert r.status_code == 400


# ────────── filter: tag operators (K!=V, !K, K=V1,V2) ──────────

async def test_filter_tag_ne_strict_excludes_null(client):
    """``K!=V`` is strict — sessions without the key at all are NOT
    matched. To include them, the caller passes --tag !K too."""
    a = await _seed(client, "ne-a")
    b = await _seed(client, "ne-b")
    c = await _seed(client, "ne-c")
    await client.patch(f"/v3/sessions/{a}/tags",
                       json={"set": {"status": "wip"}})
    await client.patch(f"/v3/sessions/{b}/tags",
                       json={"set": {"status": "draft"}})
    # `c` has no status tag at all.
    r = await client.get("/v3/sessions", params={"tag": "status!=draft"})
    body = r.json()
    # `a` matches (wip != draft); `b` doesn't (draft = draft);
    # `c` doesn't (NULL is excluded by strict NE).
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == a


async def test_filter_tag_absent(client):
    a = await _seed(client, "abs-a")
    b = await _seed(client, "abs-b")
    await client.patch(f"/v3/sessions/{a}/tags",
                       json={"set": {"project": "billing"}})
    # b is untagged.
    r = await client.get("/v3/sessions", params={"tag": "!project"})
    body = r.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == b


async def test_filter_tag_in_list(client):
    a = await _seed(client, "in-a")
    b = await _seed(client, "in-b")
    c = await _seed(client, "in-c")
    await client.patch(f"/v3/sessions/{a}/tags",
                       json={"set": {"status": "wip"}})
    await client.patch(f"/v3/sessions/{b}/tags",
                       json={"set": {"status": "review"}})
    await client.patch(f"/v3/sessions/{c}/tags",
                       json={"set": {"status": "done"}})
    r = await client.get("/v3/sessions", params={"tag": "status=wip,review"})
    body = r.json()
    sids = {s["session_id"] for s in body["sessions"]}
    assert sids == {a, b}


async def test_filter_combining_ne_and_present(client):
    """`--tag status!=draft --tag project` — "not draft AND has project"."""
    a = await _seed(client, "comb-a")
    b = await _seed(client, "comb-b")
    c = await _seed(client, "comb-c")
    await client.patch(f"/v3/sessions/{a}/tags",
                       json={"set": {"status": "wip", "project": "billing"}})
    await client.patch(f"/v3/sessions/{b}/tags",
                       json={"set": {"status": "draft", "project": "billing"}})
    await client.patch(f"/v3/sessions/{c}/tags",
                       json={"set": {"status": "wip"}})  # missing project
    r = await client.get(
        "/v3/sessions",
        params=[("tag", "status!=draft"), ("tag", "project")],
    )
    body = r.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == a


async def test_contradictory_same_key_returns_empty(client):
    """``--tag project=a --tag project=b`` is AND of two eq predicates
    → no row can satisfy both. Returns empty result, NOT an error —
    user wrote the filter, system doesn't second-guess it."""
    a = await _seed(client, "contra-a")
    await client.patch(f"/v3/sessions/{a}/tags",
                       json={"set": {"project": "billing"}})
    r = await client.get(
        "/v3/sessions",
        params=[("tag", "project=billing"), ("tag", "project=infra")],
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


async def test_filter_in_value_with_empty_member_rejected(client):
    """``K=a,,b`` is treated as a typo by the parser — 400."""
    r = await client.get("/v3/sessions", params={"tag": "status=a,,b"})
    assert r.status_code == 400


# ────────── filter: since / until ──────────

async def test_filter_since_until(client, app):
    a = await _seed(client, "t-1")
    b = await _seed(client, "t-2")
    await _set_created_at(app, a, "2026-04-01T00:00:00Z")
    await _set_created_at(app, b, "2026-05-15T00:00:00Z")

    r = await client.get("/v3/sessions", params={"since": "2026-05-01T00:00:00Z"})
    body = r.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == b

    r = await client.get("/v3/sessions", params={"until": "2026-05-01T00:00:00Z"})
    body = r.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == a


async def test_since_until_reversed_window_rejected(client):
    r = await client.get(
        "/v3/sessions",
        params={"since": "2026-06-01T00:00:00Z", "until": "2026-05-01T00:00:00Z"},
    )
    assert r.status_code == 400


async def test_invalid_iso_rejected(client):
    r = await client.get("/v3/sessions", params={"since": "yesterday"})
    assert r.status_code == 400


# ────────── response shape ──────────

async def test_response_carries_endpoint_and_tags(client):
    sid = await _seed(client, "shape-1")
    await client.patch(f"/v3/sessions/{sid}/tags",
                       json={"set": {"project": "x"}})
    body = (await client.get("/v3/sessions")).json()
    row = body["sessions"][0]
    # endpoint = source@<label-or-location>
    assert row["endpoint"].startswith("claude-code@")
    assert row["tags"] == {"project": "x"}
    assert row["round_count"] == 2
    # No rounds[] in list payload — that's a `read <sid>` concern.
    assert "rounds" not in row

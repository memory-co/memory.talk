"""POST /v3/read — card + session paths via API.

Mirrors v2's ``api/test_reads.py``: bad prefix → 400, missing → 404,
happy-path returns the expected schema. Adds v3-specific assertions:
``read_count`` bumps on card read, sessions stay completely pure.
"""
from __future__ import annotations
import datetime as _dt
import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


# ────────── session seed ──────────

async def _ingest(client, sid: str = "abc-123", sha: str = "sha1", rounds=None) -> str:
    rounds = rounds or [
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "hello world"}]},
        {"round_id": "r2", "role": "assistant",
         "content": [{"type": "text", "text": "hi back"}]},
    ]
    r = await ingest_session(client, sid, rounds=rounds)
    r.raise_for_status()
    return r.json()["session_id"]


async def _seed_card(app) -> str:
    """Insert a minimal card directly through the repo (faster than going via
    POST /v3/insights; we just want a card_id to read back)."""
    db = app.state.db
    now = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    await db.insights.insert("card_seed", "seeded insight", [
        {"role": "human", "text": "what's lancedb?",
         "session_id": "sess_abc", "index": 1},
        {"role": "assistant", "text": "embedded vector db",
         "session_id": "sess_abc", "index": 2},
    ], now)
    await db.insights.init_stats("card_seed", now)
    return "card_seed"


# ────────── read session ──────────

class TestReadSession:
    async def test_returns_full_session(self, client):
        sid = await _ingest(client)
        r = await client.post("/v3/read", json={"id": sid})
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "session"
        assert body["session"]["session_id"] == sid
        assert body["session"]["metadata"]["cwd"] == "/work/proj"
        assert len(body["session"]["rounds"]) == 2
        # Indices preserved + monotonically assigned.
        assert [r["index"] for r in body["session"]["rounds"]] == [1, 2]

    async def test_session_not_found_404(self, client):
        # Gap fill: v2 had this; missing in original v3 test_ingest_and_read.
        r = await client.post("/v3/read", json={"id": "sess_does_not_exist"})
        assert r.status_code == 404
        assert "not found" in r.json()["detail"]

    async def test_session_read_is_pure(self, app, client):
        """Sessions don't participate in forum dynamics — read must NOT
        bump any stats / write events. v2 had ``test_view_session_no_ttl_change``
        for the analogous assertion."""
        sid = await _ingest(client)
        # No card_stats row to inspect for sessions; the test is that
        # *nothing* gets mutated. Read three times and confirm the
        # only side effect we can see (no events.jsonl entries) holds.
        for _ in range(3):
            await client.post("/v3/read", json={"id": sid})
        # sessions/<source>/<bucket>/<sid>/events.jsonl should only contain
        # the `imported` event from ingest, nothing read-related.
        raw = sid[len("sess_"):]
        bucket = raw[:2].lower()
        evt_path = (
            app.state.config.data_root
            / "sessions" / "claude-code" / bucket / sid / "events.jsonl"
        )
        lines = evt_path.read_text().strip().splitlines() if evt_path.exists() else []
        event_kinds = [__import__("json").loads(l)["event"] for l in lines]
        # No `read_at` or any read-derived event on session.
        assert all(k != "read_at" for k in event_kinds)


# ────────── read card ──────────

class TestReadCard:
    async def test_returns_full_card(self, app, client):
        cid = await _seed_card(app)
        r = await client.post("/v3/read", json={"id": cid})
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "card"
        c = body["card"]
        assert c["card_id"] == cid
        assert c["insight"] == "seeded insight"
        # Stats populated; read_count bumped to 1 by this very call.
        assert c["stats"]["read_count"] == 1
        assert c["stats"]["review_count"] == 0
        assert len(c["rounds"]) == 2

    async def test_read_bumps_read_count(self, app, client):
        cid = await _seed_card(app)
        for _ in range(4):
            r = await client.post("/v3/read", json={"id": cid})
            assert r.status_code == 200
        body = r.json()
        assert body["card"]["stats"]["read_count"] == 4

    async def test_card_not_found_404(self, client):
        r = await client.post("/v3/read", json={"id": "card_doesnotexist"})
        assert r.status_code == 404


# ────────── id prefix validation ──────────

class TestPrefix:
    async def test_bad_prefix_400(self, client):
        r = await client.post("/v3/read", json={"id": "garbage_xyz"})
        assert r.status_code == 400
        assert "invalid id prefix" in r.json()["detail"]

    async def test_missing_id_field(self, client):
        # Pydantic validation error → 422.
        r = await client.post("/v3/read", json={})
        assert r.status_code == 422

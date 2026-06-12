"""Lock in v3's three-target storage layout:

- SQLite has ``sessions`` only (round-level metadata sits in
  ``sessions.last_round_id`` + the jsonl mirror). No ``rounds`` /
  ``rounds_index`` SQL tables.
- LanceDB has a per-round ``rounds`` table with FTS-friendly text + vector.
- The jsonl file is the source of truth for full round content.
"""
from __future__ import annotations
import json

import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


_SAMPLE_ROUNDS = [
    {"round_id": "r1", "role": "human",
     "content": [{"type": "text", "text": "first message"}]},
    {"round_id": "r2", "role": "assistant",
     "content": [{"type": "text", "text": "second message with LanceDB keyword"}]},
]


async def _ingest_sample(client) -> str:
    r = await ingest_session(client, "layout-1", rounds=_SAMPLE_ROUNDS)
    assert r.status_code == 200
    return r.json()["session_id"]


async def test_sqlite_has_no_rounds_table(app, client):
    await _ingest_sample(client)
    db = app.state.db
    async with db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rounds'"
    ) as cur:
        row = await cur.fetchone()
    assert row is None, "v3 should not have a `rounds` SQL table"


async def test_sqlite_sessions_tracks_last_round_id(app, client):
    """``sessions.last_round_id`` is the cursor IngestService checks for
    optimistic concurrency on append. After this ingest it must point at
    the last round we sent (``r2``)."""
    sid = await _ingest_sample(client)
    db = app.state.db
    row = await db.sessions.get(sid)
    assert row["round_count"] == 2
    assert row["last_round_id"] == "r2"


async def test_sqlite_has_no_rounds_index_table(app, client):
    """``rounds_index`` was dropped — content-hash overwrite detection
    no longer exists. Append-only semantics + last_round_id replace it."""
    await _ingest_sample(client)
    db = app.state.db
    async with db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rounds_index'"
    ) as cur:
        assert await cur.fetchone() is None


async def test_rounds_jsonl_is_source_of_truth(client, data_root):
    sid = await _ingest_sample(client)
    from memorytalk.repository.sessions import SessionStore
    bucket = SessionStore._bucket(sid)
    jsonl = data_root / "sessions" / "claude-code" / bucket / sid / "rounds.jsonl"
    assert jsonl.exists()
    lines = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
    assert [l["idx"] for l in lines] == [1, 2]
    assert "second message with LanceDB keyword" in lines[1]["text"]


async def test_lancedb_rounds_table_has_one_row_per_round(app, client):
    from memorytalk.service.searchbase_schema import ROUNDS

    sid = await _ingest_sample(client)
    searchbase = app.state.searchbase
    if searchbase is None:
        pytest.skip("searchbase not available in this environment")
    # One indexed row per round (id = f"{sid}:{idx}").
    assert await searchbase.count(ROUNDS, {"session_id": sid}) == 2


async def test_appended_round_lands_in_all_three_stores(app, client):
    sid = await _ingest_sample(client)
    extra_rounds = _SAMPLE_ROUNDS + [
        {"round_id": "r3", "role": "human",
         "content": [{"type": "text", "text": "third message"}]},
    ]
    r = await ingest_session(client, "layout-1", rounds=extra_rounds)
    body = r.json()
    assert body["status"] == "ok"
    assert body["appended_count"] == 1

    db = app.state.db
    s = await db.sessions.get(sid)
    assert s["round_count"] == 3
    assert s["last_round_id"] == "r3"

    rounds = await db.sessions.read_rounds_file("claude-code", sid)
    assert len(rounds) == 3
    assert rounds[-1]["idx"] == 3

    from memorytalk.service.searchbase_schema import ROUNDS
    searchbase = app.state.searchbase
    if searchbase is not None:
        assert await searchbase.count(ROUNDS, {"session_id": sid}) == 3

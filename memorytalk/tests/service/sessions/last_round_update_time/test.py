"""last_round_update_time — maintained on append + backfilled. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def test_append_sets_last_round_update_time_to_temporal_max(app, client):
    r = await ingest_session(client, "lrut-1", rounds=[
        {"round_id": "r1", "role": "human", "timestamp": "2026-05-20T10:00:00Z",
         "content": [{"type": "text", "text": "hi"}]},
        {"round_id": "r2", "role": "assistant",
         "timestamp": "2026-05-20T20:00:00+08:00",   # == 12:00 UTC (later)
         "content": [{"type": "text", "text": "yo"}]},
    ])
    sid = r.json()["session_id"]
    row = await app.state.db.sessions.get(sid)
    assert row["last_round_update_time"] == "2026-05-20T12:00:00Z"


async def test_backfill_fills_null_rows_from_rounds_jsonl(app, client):
    r = await ingest_session(client, "lrut-bf", rounds=[
        {"round_id": "r1", "role": "human", "timestamp": "2026-05-20T10:00:00Z",
         "content": [{"type": "text", "text": "a"}]},
        {"round_id": "r2", "role": "assistant", "timestamp": "2026-05-20T11:00:00Z",
         "content": [{"type": "text", "text": "b"}]},
    ])
    sid = r.json()["session_id"]
    db = app.state.db
    await db.sessions.conn.execute(
        "UPDATE sessions SET last_round_update_time = NULL WHERE session_id = ?",
        (sid,),
    )
    await db.sessions.conn.commit()

    n = await db.sessions.backfill_last_round_update_time()

    assert n == 1
    row = await db.sessions.get(sid)
    assert row["last_round_update_time"] == "2026-05-20T11:00:00Z"

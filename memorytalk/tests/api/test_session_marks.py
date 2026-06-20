"""/v4 session marks — POST submit, GET list, read sess_…#m<n> end-to-end."""
from __future__ import annotations

import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def _session(client, sid="mark-src", n=5) -> str:
    rounds = [
        {"round_id": f"r{i}", "role": "human" if i % 2 else "assistant",
         "content": [{"type": "text", "text": f"round {i} about pty and tmux"}]}
        for i in range(1, n + 1)
    ]
    r = await ingest_session(client, sid, rounds=rounds)
    r.raise_for_status()
    return r.json()["session_id"]


async def test_submit_marks_creates_card_and_lists(client):
    sid = await _session(client)
    body = {
        "last_index": 5,
        "description": "reading the pty/tmux stretch",
        "marks": [
            {"id": "m1", "indexes": "3-4",
             "mark": "user pivoted. #why does pty remind the user of tmux？ wants reconnect"},
            {"id": "m2", "mark": "this part is just EMFILE triage, no question."},
        ],
    }
    r = await client.post(f"/v4/sessions/{sid}/marks", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"] == sid
    assert data["last_index"] == 5
    m1, m2 = data["marks"]
    assert m1["mark"] == "m1"
    assert len(m1["issues"]) == 1
    assert m1["issues"][0]["is_new"] is True
    assert m1["issues"][0]["card_id"].startswith("card_")
    assert m1["issues"][0]["indexes"] == "3-4"
    assert m2["issues"] == []

    # GET list reflects the two marks (metadata only).
    g = await client.get(f"/v4/sessions/{sid}/marks")
    assert g.status_code == 200
    marks = g.json()["marks"]
    assert [m["mark"] for m in marks] == ["m1", "m2"]
    assert all(m["last_index"] == 5 and m["created_at"] for m in marks)


async def test_read_mark_fragment(client):
    sid = await _session(client)
    await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "scene",
        "marks": [{"id": "m1", "indexes": "1-2", "mark": "#a fresh question？"}],
    })
    r = await client.post("/v4/read", json={"id": f"{sid}#m1"})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["type"] == "mark"
    mk = payload["mark"]
    assert mk["description"] == "scene"
    assert mk["last_index"] == 5
    assert mk["indexes"] == "1-2"
    assert mk["issues"][0]["is_new"] is True
    assert mk["mark"] == "#a fresh question？"


async def test_read_missing_mark_404(client):
    sid = await _session(client)
    r = await client.post("/v4/read", json={"id": f"{sid}#m9"})
    assert r.status_code == 404


async def test_optimistic_lock_409(client):
    sid = await _session(client)   # round_count == 5
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 4, "description": "stale",
        "marks": [{"id": "m1", "mark": "x"}],
    })
    assert r.status_code == 409


async def test_id_not_monotonic_400(client):
    sid = await _session(client)
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "x",
        "marks": [{"id": "m2", "mark": "skips m1"}],
    })
    assert r.status_code == 400


async def test_empty_marks_400(client):
    sid = await _session(client)
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "x", "marks": [],
    })
    assert r.status_code == 400


async def test_unknown_session_404(client):
    r = await client.post("/v4/sessions/sess-nope0000/marks", json={
        "last_index": 0, "description": "x", "marks": [{"id": "m1", "mark": "x"}],
    })
    assert r.status_code == 404


async def test_hit_links_on_second_submit(client):
    sid = await _session(client)
    r1 = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "first",
        "marks": [{"id": "m1", "indexes": "1", "mark": "#what is the capital of France？"}],
    })
    card_id = r1.json()["marks"][0]["issues"][0]["card_id"]
    r2 = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "second",
        "marks": [{"id": "m2", "indexes": "2", "mark": "#what is the capital of France？"}],
    })
    iss = r2.json()["marks"][0]["issues"][0]
    assert iss["is_new"] is False
    assert iss["card_id"] == card_id

    # The card's reverse provenance shows both marks.
    cr = await client.post("/v4/read", json={"id": card_id})
    sessions = cr.json()["card"]["sessions"]
    assert {s["mark"] for s in sessions} == {"m1", "m2"}

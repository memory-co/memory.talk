"""/v4 session marks — POST submit, GET list, DELETE clear, read sess_…#m<n>."""
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


def _full_rounds(n, overrides=None):
    """A round entry per index 1..n (100% coverage); ``overrides`` patches
    specific indexes, e.g. ``{3: {"comment": "#q？"}}``."""
    overrides = overrides or {}
    out = []
    for i in range(1, n + 1):
        entry = {"index": i}
        if i in overrides:
            entry.update(overrides[i])
        out.append(entry)
    return out


async def test_submit_marks_creates_card_auto_m1(client):
    sid = await _session(client)
    body = {
        "last_index": 5,
        "description": "reading the pty/tmux stretch",
        "rounds": _full_rounds(5, {
            3: {"comment": "user pivoted. #why does pty remind the user of tmux？ wants reconnect"},
        }),
    }
    r = await client.post(f"/v4/sessions/{sid}/marks", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"] == sid
    assert data["mark"] == "m1"          # server auto-assigned
    rounds = data["rounds"]
    assert len(rounds) == 5
    r3 = next(rd for rd in rounds if rd["index"] == 3)
    assert len(r3["issues"]) == 1
    assert r3["issues"][0]["is_new"] is True
    assert r3["issues"][0]["card_id"].startswith("card_")
    assert r3["issues"][0]["indexes"] == "3"
    # rounds with no comment have empty issues
    assert next(rd for rd in rounds if rd["index"] == 1)["issues"] == []

    # GET list reflects one mark (metadata only).
    g = await client.get(f"/v4/sessions/{sid}/marks")
    assert g.status_code == 200
    marks = g.json()["marks"]
    assert [m["mark"] for m in marks] == ["m1"]
    assert marks[0]["last_index"] == 5 and marks[0]["created_at"]


async def test_second_submit_is_m2(client):
    sid = await _session(client)
    await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "first pass",
        "rounds": _full_rounds(5),
    })
    r2 = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "second pass",
        "rounds": _full_rounds(5),
    })
    assert r2.status_code == 200, r2.text
    assert r2.json()["mark"] == "m2"
    g = await client.get(f"/v4/sessions/{sid}/marks")
    assert [m["mark"] for m in g.json()["marks"]] == ["m1", "m2"]


async def test_read_mark_fragment(client):
    sid = await _session(client)
    await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "scene",
        "rounds": _full_rounds(5, {1: {"comment": "#a fresh question？"}}),
    })
    r = await client.post("/v4/read", json={"id": f"{sid}#m1"})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["type"] == "mark"
    mk = payload["mark"]
    assert mk["description"] == "scene"
    assert mk["last_index"] == 5
    assert len(mk["rounds"]) == 5
    r1 = next(rd for rd in mk["rounds"] if rd["index"] == 1)
    assert r1["comment"] == "#a fresh question？"
    assert r1["issues"][0]["is_new"] is True


async def test_session_read_includes_marks(client):
    sid = await _session(client)
    await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "scene",
        "rounds": _full_rounds(5, {
            3: {"comment": "user pivoted. #why does pty remind of tmux？"},
        }),
    })
    r = await client.post("/v4/read", json={"id": sid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "session"
    marks = body["session"]["marks"]
    assert [m["mark"] for m in marks] == ["m1"]
    m1 = marks[0]
    assert m1["description"] == "scene"
    assert m1["last_index"] == 5
    r3 = next(rd for rd in m1["rounds"] if rd["index"] == 3)
    assert "#why does pty remind of tmux？" in r3["comment"]
    assert r3["issues"][0]["is_new"] is True
    assert r3["issues"][0]["card_id"].startswith("card_")


async def test_session_read_no_marks_field_empty(client):
    sid = await _session(client)
    r = await client.post("/v4/read", json={"id": sid})
    assert r.status_code == 200
    assert r.json()["session"]["marks"] == []


async def test_read_missing_mark_404(client):
    sid = await _session(client)
    r = await client.post("/v4/read", json={"id": f"{sid}#m9"})
    assert r.status_code == 404


async def test_optimistic_lock_409(client):
    sid = await _session(client)   # round_count == 5
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 4, "description": "stale",
        "rounds": _full_rounds(4),
    })
    assert r.status_code == 409


async def test_first_index_must_be_1_400(client):
    sid = await _session(client)
    # Start at round 2 → skipping round 1 → reject.
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "starts mid-session",
        "rounds": [{"index": i} for i in range(2, 6)],
    })
    assert r.status_code == 400
    assert "first round index must be 1" in r.text


async def test_not_strictly_ascending_400(client):
    sid = await _session(client)
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "out of order",
        "rounds": [{"index": 1}, {"index": 3}, {"index": 2}, {"index": 4}, {"index": 5}],
    })
    assert r.status_code == 400
    assert "ascending" in r.text


async def test_duplicate_index_400(client):
    sid = await _session(client)
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "dup",
        "rounds": [{"index": 1}, {"index": 2}, {"index": 2}, {"index": 3}, {"index": 4}, {"index": 5}],
    })
    assert r.status_code == 400


async def test_empty_rounds_400(client):
    sid = await _session(client)
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "x", "rounds": [],
    })
    assert r.status_code == 400


async def test_coverage_below_threshold_400_nothing_persisted(client):
    sid = await _session(client)   # round_count == 5
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "skimmed",
        "rounds": [{"index": 1, "comment": "#a question？"}],   # 1/5 = 20%
    })
    assert r.status_code == 400
    assert "coverage" in r.text and "90%" in r.text
    # nothing persisted
    g = await client.get(f"/v4/sessions/{sid}/marks")
    assert g.json()["marks"] == []


async def test_coverage_at_threshold_passes(client):
    sid = await _session(client, n=10)   # 90% of 10 = 9 rounds
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 10, "description": "read 9/10",
        "rounds": [{"index": i} for i in range(1, 10)],   # 1..9 = 9/10 = 90%
    })
    assert r.status_code == 200, r.text
    assert r.json()["mark"] == "m1"


async def test_no_comment_rounds_no_card(client):
    sid = await _session(client)
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "read all, nothing to note",
        "rounds": _full_rounds(5),
    })
    assert r.status_code == 200, r.text
    assert all(rd["issues"] == [] for rd in r.json()["rounds"])


async def test_comment_issue_grounds_at_round(client):
    sid = await _session(client)
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "comment issue",
        "rounds": _full_rounds(5, {4: {"comment": "#what is the capital of France？"}}),
    })
    card_id = next(rd for rd in r.json()["rounds"] if rd["index"] == 4)["issues"][0]["card_id"]
    # card_sessions row grounds at the round's own index "4"
    cr = await client.post("/v4/read", json={"id": card_id})
    sessions = cr.json()["card"]["sessions"]
    assert any(s["mark"] == "m1" and s["indexes"] == "4" for s in sessions)


async def test_explicit_issue_grounds_at_given_indexes(client):
    sid = await _session(client)
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "explicit issue",
        "rounds": _full_rounds(5, {
            5: {"issues": [{"issue": "what caused the EMFILE", "indexes": "2-3"}]},
        }),
    })
    assert r.status_code == 200, r.text
    r5 = next(rd for rd in r.json()["rounds"] if rd["index"] == 5)
    iss = r5["issues"][0]
    assert iss["indexes"] == "2-3"
    cr = await client.post("/v4/read", json={"id": iss["card_id"]})
    sessions = cr.json()["card"]["sessions"]
    assert any(s["mark"] == "m1" and s["indexes"] == "2-3" for s in sessions)


async def test_same_card_two_rounds_merges_indexes(client):
    sid = await _session(client)
    # Rounds 2 & 4 ask the SAME question → one card, ONE card_sessions row
    # with merged indexes "2,4".
    q = "#why does pty remind of tmux？"
    r = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "same q twice",
        "rounds": _full_rounds(5, {2: {"comment": q}, 4: {"comment": q}}),
    })
    assert r.status_code == 200, r.text
    card_id = next(rd for rd in r.json()["rounds"] if rd["index"] == 2)["issues"][0]["card_id"]
    cr = await client.post("/v4/read", json={"id": card_id})
    sessions = [s for s in cr.json()["card"]["sessions"] if s["mark"] == "m1"]
    assert len(sessions) == 1                      # ONE row (PK merge)
    assert sessions[0]["indexes"] == "2,4"


async def test_unknown_session_404(client):
    r = await client.post("/v4/sessions/sess-nope0000/marks", json={
        "last_index": 0, "description": "x",
        "rounds": [{"index": 1, "comment": "x"}],
    })
    assert r.status_code == 404


async def test_hit_links_on_second_submit(client):
    sid = await _session(client)
    r1 = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "first",
        "rounds": _full_rounds(5, {1: {"comment": "#what is the capital of France？"}}),
    })
    card_id = next(rd for rd in r1.json()["rounds"] if rd["index"] == 1)["issues"][0]["card_id"]
    r2 = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "second",
        "rounds": _full_rounds(5, {2: {"comment": "#what is the capital of France？"}}),
    })
    iss = next(rd for rd in r2.json()["rounds"] if rd["index"] == 2)["issues"][0]
    assert iss["is_new"] is False
    assert iss["card_id"] == card_id

    # The card's reverse provenance shows both marks.
    cr = await client.post("/v4/read", json={"id": card_id})
    sessions = cr.json()["card"]["sessions"]
    assert {s["mark"] for s in sessions} == {"m1", "m2"}


# ────────── DELETE clear-marks ──────────

async def test_delete_clears_marks_but_leaves_cards(client):
    sid = await _session(client)
    sub = await client.post(f"/v4/sessions/{sid}/marks", json={
        "last_index": 5, "description": "to be cleared",
        "rounds": _full_rounds(5, {3: {"comment": "#a brand new question？"}}),
    })
    card_id = next(rd for rd in sub.json()["rounds"] if rd["index"] == 3)["issues"][0]["card_id"]

    d = await client.delete(f"/v4/sessions/{sid}/marks")
    assert d.status_code == 200, d.text
    assert d.json() == {"session_id": sid, "deleted_marks": 1}

    # marks gone (session_marks + card_sessions)
    g = await client.get(f"/v4/sessions/{sid}/marks")
    assert g.json()["marks"] == []
    rm = await client.post("/v4/read", json={"id": f"{sid}#m1"})
    assert rm.status_code == 404
    # card itself survives — only the provenance edge went
    cr = await client.post("/v4/read", json={"id": card_id})
    assert cr.status_code == 200
    assert cr.json()["card"]["sessions"] == []


async def test_delete_no_marks_is_noop(client):
    sid = await _session(client)
    d = await client.delete(f"/v4/sessions/{sid}/marks")
    assert d.status_code == 200
    assert d.json() == {"session_id": sid, "deleted_marks": 0}


async def test_delete_unknown_session_404(client):
    d = await client.delete("/v4/sessions/sess-nope0000/marks")
    assert d.status_code == 404

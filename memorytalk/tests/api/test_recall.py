"""POST /v4/recall — hybrid card retrieval with per-session dedup.

0.9.0: caller MUST send ``source`` so the server can compute the
canonical session_id correctly. ``recall_count`` is now derived from
``recall_event`` on read (no longer a ``card_stats`` column).
"""
from __future__ import annotations
import pytest

from memorytalk.adapters import get_adapter
from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def _ingest(client) -> str:
    r = await ingest_session(client, "rc-src", metadata={"cwd": "/work"}, rounds=[
        {"round_id": "r1", "role": "human",
         "content": [{"type": "text", "text": "intro about LanceDB"}]},
    ])
    r.raise_for_status()
    return r.json()["session_id"]


async def _make_card(client, sid: str, insight: str) -> str:
    r = await client.post("/v4/insights", json={
        "insight": insight,
        "rounds": [{"session_id": sid, "indexes": "1"}],
    })
    r.raise_for_status()
    return r.json()["card_id"]


def _canonical(raw_id: str, source: str = "claude-code") -> str:
    return get_adapter(source).mint_session_id(raw_id)


async def test_recall_basic_returns_card_with_insight(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid, "LanceDB is the choice")
    r = await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "hook-1",
        "prompt": "LanceDB",
        "top_k": 5,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == _canonical("hook-1")
    assert body["query"] == "LanceDB"
    ids = [c["card_id"] for c in body["recalled"]]
    assert cid in ids


async def test_recall_dedup_within_same_session(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid, "LanceDB choice")
    hook_sid = "hook-dedup-1"

    r1 = await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": hook_sid, "prompt": "LanceDB", "top_k": 5,
    })
    assert cid in [c["card_id"] for c in r1.json()["recalled"]]

    r2 = await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": hook_sid, "prompt": "LanceDB", "top_k": 5,
    })
    body2 = r2.json()
    assert cid not in [c["card_id"] for c in body2["recalled"]]
    assert cid in body2["skipped_already_recalled"]


async def test_recall_dedup_resets_for_new_session(client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid, "lancedb take 2")
    await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "hook-A", "prompt": "lancedb", "top_k": 5,
    })
    r = await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "hook-B", "prompt": "lancedb", "top_k": 5,
    })
    ids = [c["card_id"] for c in r.json()["recalled"]]
    assert cid in ids


async def test_recall_count_derived_from_recall_event(app, client):
    """``card_stats.recall_count`` is gone; the value is derived on read
    from ``recall_event``. Verify the derived counter reflects every
    NEW returned card (not skipped) across sessions."""
    sid = await _ingest(client)
    cid = await _make_card(client, sid, "lancedb count")
    db = app.state.db

    counts0 = await db.recall.recall_counts([cid])
    assert counts0[cid] == 0

    await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "hook-count-1", "prompt": "lancedb", "top_k": 5,
    })
    counts1 = await db.recall.recall_counts([cid])
    assert counts1[cid] == 1

    # dedup'd repeat (same session) → NOT bumped
    await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "hook-count-1", "prompt": "lancedb", "top_k": 5,
    })
    counts2 = await db.recall.recall_counts([cid])
    assert counts2[cid] == 1

    # new session → fresh dedup → bumped
    await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "hook-count-2", "prompt": "lancedb", "top_k": 5,
    })
    counts3 = await db.recall.recall_counts([cid])
    assert counts3[cid] == 2


async def test_recall_does_not_touch_search_log(app, client):
    sid = await _ingest(client)
    await _make_card(client, sid, "lancedb x")
    await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "no-audit", "prompt": "lancedb",
    })
    n = await app.state.db.search_log.count()
    assert n == 0


async def test_recall_session_id_canonicalized_via_adapter(client):
    """``source`` selects the adapter that mints the canonical id —
    same raw id under different sources MUST land at different
    canonicals (different loc_code)."""
    sid = await _ingest(client)
    await _make_card(client, sid, "norm-1")
    r_cc = await client.post("/v4/recall", json={
        "source": "claude-code", "session_id": "raw-id", "prompt": "norm",
    })
    r_codex = await client.post("/v4/recall", json={
        "source": "codex", "session_id": "raw-id", "prompt": "norm",
    })
    assert r_cc.json()["session_id"] == _canonical("raw-id", "claude-code")
    assert r_codex.json()["session_id"] == _canonical("raw-id", "codex")
    # And they MUST differ — the 0.8.x bug was exactly that they
    # collided because hook hardcoded the claude-code adapter.
    assert r_cc.json()["session_id"] != r_codex.json()["session_id"]


async def test_recall_session_in_db_not_required(client):
    sid = await _ingest(client)
    await _make_card(client, sid, "exists")
    r = await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "totally-new-session-not-in-db",
        "prompt": "exists",
    })
    assert r.status_code == 200
    assert r.json()["recalled"]


async def test_recall_empty_prompt_rejected(client):
    r = await client.post("/v4/recall", json={
        "source": "claude-code", "session_id": "x", "prompt": "",
    })
    assert r.status_code == 400


async def test_recall_unknown_source_rejected(client):
    r = await client.post("/v4/recall", json={
        "source": "definitely-not-an-adapter",
        "session_id": "x", "prompt": "hi",
    })
    assert r.status_code == 400


async def test_recall_missing_source_rejected_by_pydantic(client):
    r = await client.post("/v4/recall", json={
        "session_id": "x", "prompt": "hi",
    })
    assert r.status_code == 422  # FastAPI request validation


async def test_recall_returns_empty_when_no_matches(client):
    r = await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "lonely", "prompt": "this-keyword-matches-nothing-zzz",
    })
    body = r.json()
    assert body["recalled"] == []
    assert body["skipped_already_recalled"] == []


async def test_recall_top_k_caps_returned_results(client):
    sid = await _ingest(client)
    for i in range(5):
        await _make_card(client, sid, f"lancedb fact {i}")
    r = await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "cap-1", "prompt": "lancedb", "top_k": 2,
    })
    assert len(r.json()["recalled"]) <= 2


async def test_recall_writes_canonical_file(app, client, tmp_path):
    """0.9.0: recall.jsonl is the canonical store. Verify a file line
    appears in the per-session dir matching the canonical session_id."""
    sid = await _ingest(client)
    await _make_card(client, sid, "file-canonical-marker")
    r = await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "file-test", "prompt": "file-canonical-marker",
    })
    assert r.status_code == 200
    canonical = _canonical("file-test")
    bucket = canonical[len("sess_"):][:2] if canonical.startswith("sess_") else canonical[:2]
    data_root = app.state.config.data_root
    recall_jsonl = (
        data_root / "sessions" / "claude-code" / bucket / canonical / "recall.jsonl"
    )
    assert recall_jsonl.exists(), f"expected file at {recall_jsonl}"
    import json
    lines = [json.loads(l) for l in recall_jsonl.read_text().splitlines() if l.strip()]
    assert len(lines) >= 1
    ev = lines[-1]
    assert ev["source"] == "claude-code"
    assert ev["session_id"] == canonical
    assert ev["prompt"] == "file-canonical-marker"
    assert ev["returned"], "returned cards should include the matching one"
    # Each card slot must include both id and insight snapshot.
    for c in ev["returned"]:
        assert "card_id" in c and "insight" in c

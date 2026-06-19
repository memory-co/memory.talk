"""DELETE /v4/insights/{card_id} — hard delete contract.

Covers:
- happy path: card row gone, vector gone, files gone
- 404 on unknown card
- inbound_refs_dangling surfacing (referenced-by count) but NOT cascade
- recall_event history preserved (deleting a card doesn't rewrite history)
"""
from __future__ import annotations
import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def _ingest(client) -> str:
    rounds = [
        {"round_id": f"r{i}", "role": "human" if i % 2 else "assistant",
         "content": [{"type": "text", "text": f"round {i} body"}]}
        for i in range(1, 4)
    ]
    r = await ingest_session(client, "del-src", rounds=rounds)
    r.raise_for_status()
    return r.json()["session_id"]


async def _make_card(client, sid: str, insight: str = "x", *, indexes: str = "1") -> str:
    r = await client.post("/v4/insights", json={
        "insight": insight,
        "rounds": [{"session_id": sid, "indexes": indexes}],
    })
    r.raise_for_status()
    return r.json()["card_id"]


async def test_delete_unknown_card_404(client):
    r = await client.delete("/v4/insights/card_nope")
    assert r.status_code == 404


async def test_delete_removes_card_row(app, client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid)

    r = await client.delete(f"/v4/insights/{cid}")
    assert r.status_code == 200
    body = r.json()
    assert body["card_id"] == cid
    assert body["inbound_refs_dangling"] == 0

    # POST /v4/read on a deleted card → 404
    rd = await client.post("/v4/read", json={"id": cid})
    assert rd.status_code == 404


async def test_delete_surfaces_inbound_refs_dangling_but_does_not_cascade(
    app, client,
):
    sid = await _ingest(client)
    parent = await _make_card(client, sid, insight="parent")
    # child references parent via source_cards.
    r = await client.post("/v4/insights", json={
        "insight": "child of parent",
        "rounds": [{"session_id": sid, "indexes": "2"}],
        "source_cards": [{"card_id": parent, "relation": "derives_from"}],
    })
    r.raise_for_status()
    child = r.json()["card_id"]

    r = await client.delete(f"/v4/insights/{parent}")
    assert r.status_code == 200
    assert r.json()["inbound_refs_dangling"] == 1, (
        "the child's source_cards still points at deleted parent"
    )

    # Child must STILL EXIST (not cascade-deleted).
    rd = await client.post("/v4/read", json={"id": child})
    assert rd.status_code == 200, (
        "deleting a card must not cascade-delete its referencers"
    )


async def test_delete_removes_vector_so_search_does_not_return_it(app, client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid, insight="LanceDB unique-needle marker")

    # Sanity: search returns it pre-delete.
    pre = await client.post("/v4/search", json={"query": "unique-needle"})
    pre_ids = [it.get("card_id") for it in pre.json()["results"] if it["type"] == "card"]
    assert cid in pre_ids

    await client.delete(f"/v4/insights/{cid}")

    post = await client.post("/v4/search", json={"query": "unique-needle"})
    post_ids = [it.get("card_id") for it in post.json()["results"] if it["type"] == "card"]
    assert cid not in post_ids, "deleted card must not appear in search results"


async def test_delete_does_not_rewrite_recall_event_history(app, client):
    """recall_event is the audit trail of "what was shown when".
    Deleting a card doesn't erase the fact that it WAS recalled."""
    sid = await _ingest(client)
    cid = await _make_card(client, sid, insight="recallable")

    # Trigger a recall that returns this card.
    rr = await client.post("/v4/recall", json={
        "source": "claude-code",
        "session_id": "del-recall-1",
        "prompt": "recallable",
    })
    assert rr.status_code == 200
    assert cid in [c["card_id"] for c in rr.json()["recalled"]]

    # Delete the card.
    r = await client.delete(f"/v4/insights/{cid}")
    assert r.status_code == 200

    # recall_event row still has this card_id in returned_ids.
    rows = await app.state.db.recall.get_session_events(
        rr.json()["session_id"], limit=10,
    )
    assert any(cid in row["returned_ids"] for row in rows), (
        "recall_event history must NOT be rewritten by card delete"
    )


async def test_delete_removes_file_dir(app, client):
    sid = await _ingest(client)
    cid = await _make_card(client, sid)

    bucket = cid[len("card_"):][:2].lower()
    card_dir = app.state.config.data_root / "insights" / bucket / cid
    assert card_dir.exists(), "sanity: card dir should exist before delete"

    await client.delete(f"/v4/insights/{cid}")

    assert not card_dir.exists(), "card dir must be rmtree'd after delete"


async def test_delete_is_not_idempotent(app, client):
    """Second DELETE of a now-missing card returns 404 — we don't silently
    no-op because callers should not be calling us twice."""
    sid = await _ingest(client)
    cid = await _make_card(client, sid)
    r1 = await client.delete(f"/v4/insights/{cid}")
    assert r1.status_code == 200
    r2 = await client.delete(f"/v4/insights/{cid}")
    assert r2.status_code == 404

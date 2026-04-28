"""Smoke tests for write endpoints wired through FastAPI."""
from __future__ import annotations


def _ingest(client, session_id="platform-abc", sha256="h1"):
    return client.post("/v2/sessions", json={
        "session_id": session_id, "source": "claude-code",
        "created_at": "2026-04-10T00:00:00Z",
        "metadata": {"project": "demo"}, "sha256": sha256,
        "rounds": [
            {"round_id": "r1", "parent_id": None, "timestamp": "",
             "speaker": "user", "role": "human",
             "content": [{"type": "text", "text": "hi"}], "is_sidechain": False},
            {"round_id": "r2", "parent_id": "r1", "timestamp": "",
             "speaker": "assistant", "role": "assistant",
             "content": [{"type": "text", "text": "yo"}], "is_sidechain": False},
        ],
    })


def test_sessions_then_cards_then_tags_then_links(app_client):
    r = _ingest(app_client)
    assert r.status_code == 200
    sid = r.json()["session_id"]

    # Create a card referencing rounds 1-2
    r = app_client.post("/v2/cards", json={
        "summary": "decided on LanceDB",
        "rounds": [{"session_id": sid, "indexes": "1-2"}],
    })
    assert r.status_code == 200, r.text
    card_id = r.json()["card_id"]

    # Tag the session
    r = app_client.post("/v2/tags/add", json={"session_id": sid, "tags": ["decision"]})
    assert r.status_code == 200
    assert r.json()["tags"] == ["decision"]

    # Bad prefix (card) → 400
    r = app_client.post("/v2/tags/add", json={"session_id": card_id, "tags": ["x"]})
    assert r.status_code == 400

    # Create a card-to-session link
    r = app_client.post("/v2/links", json={
        "source_id": card_id, "source_type": "card",
        "target_id": sid, "target_type": "session",
        "comment": "extracted from here",
    })
    assert r.status_code == 200
    assert r.json()["ttl"] > 0

    # Self-loop 400
    r = app_client.post("/v2/links", json={
        "source_id": card_id, "source_type": "card",
        "target_id": card_id, "target_type": "card",
    })
    assert r.status_code == 400


def test_cards_out_of_range_400(app_client):
    _ingest(app_client)
    # Session only has 2 rounds; asking for 1-99 should 400
    r = app_client.post("/v2/cards", json={
        "summary": "x",
        "rounds": [{"session_id": "sess_platform-abc", "indexes": "1-99"}],
    })
    assert r.status_code == 400
    assert "out of range" in r.json()["detail"]


def test_card_conflict_409(app_client):
    r = _ingest(app_client)
    sid = r.json()["session_id"]
    first = app_client.post("/v2/cards", json={
        "summary": "a", "card_id": "card_FIXED_X",
        "rounds": [{"session_id": sid, "indexes": "1-2"}],
    })
    assert first.status_code == 200
    dup = app_client.post("/v2/cards", json={
        "summary": "b", "card_id": "card_FIXED_X",
        "rounds": [{"session_id": sid, "indexes": "1-2"}],
    })
    assert dup.status_code == 409

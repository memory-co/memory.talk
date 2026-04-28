"""Smoke tests for read endpoints wired through FastAPI."""
from __future__ import annotations


def _setup(client):
    client.post("/v2/sessions", json={
        "session_id": "platform-xy", "source": "claude-code",
        "created_at": "2026-04-10T00:00:00Z", "metadata": {}, "sha256": "h",
        "rounds": [
            {"round_id": "r1", "parent_id": None, "timestamp": "",
             "speaker": "user", "role": "human",
             "content": [{"type": "text", "text": "we picked LanceDB"}],
             "is_sidechain": False},
        ],
    })
    r = client.post("/v2/cards", json={
        "summary": "selected LanceDB for vector",
        "rounds": [{"session_id": "sess_platform-xy", "indexes": "1"}],
    })
    return "sess_platform-xy", r.json()["card_id"]


def test_view_card(app_client):
    sid, card_id = _setup(app_client)
    r = app_client.post("/v2/view", json={"id": card_id})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "card"
    assert data["card"]["card_id"] == card_id
    # Default link visible with ttl=0
    assert any(l["ttl"] == 0 and l["target_id"] == sid for l in data["links"])


def test_view_session(app_client):
    sid, _ = _setup(app_client)
    r = app_client.post("/v2/view", json={"id": sid})
    assert r.status_code == 200
    assert r.json()["type"] == "session"
    assert r.json()["session"]["rounds"][0]["index"] == 1


def test_view_bad_prefix_400(app_client):
    r = app_client.post("/v2/view", json={"id": "foo_bar"})
    assert r.status_code == 400


def test_view_not_found_404(app_client):
    r = app_client.post("/v2/view", json={"id": "card_does_not_exist"})
    assert r.status_code == 404


def test_log_events_ordered(app_client):
    sid, card_id = _setup(app_client)
    r = app_client.post("/v2/log", json={"id": sid})
    assert r.status_code == 200
    kinds = [e["kind"] for e in r.json()["events"]]
    assert "imported" in kinds and "card_extracted" in kinds


def test_search_runs_and_persists(app_client):
    _setup(app_client)
    r = app_client.post("/v2/search", json={"query": "LanceDB"})
    assert r.status_code == 200
    data = r.json()
    assert data["search_id"].startswith("sch_")
    # Status should report 1 search
    st = app_client.get("/v2/status")
    assert st.json()["searches_total"] == 1


def test_search_dsl_error_400(app_client):
    r = app_client.post("/v2/search", json={"query": "x", "where": "bogus = 'x'"})
    assert r.status_code == 400

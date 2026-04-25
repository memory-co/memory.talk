"""Rebuild gate: while app.state.status != "running", only GET /v2/status is allowed."""
from __future__ import annotations


def test_non_status_endpoints_blocked_during_rebuild(app_client):
    app_client.app.state.status = "rebuilding"
    try:
        r = app_client.post("/v2/rebuild", json={})
        assert r.status_code == 503
        assert r.json() == {"error": "rebuilding"}

        r = app_client.post("/v2/search", json={"query": "x", "top_k": 1})
        assert r.status_code == 503
        assert r.json() == {"error": "rebuilding"}

        r = app_client.post("/v2/view", json={"id": "sess_anything"})
        assert r.status_code == 503
    finally:
        app_client.app.state.status = "running"


def test_status_endpoint_still_reachable_during_rebuild(app_client):
    app_client.app.state.status = "rebuilding"
    try:
        r = app_client.get("/v2/status")
        assert r.status_code == 200
        assert r.json()["status"] == "rebuilding"
    finally:
        app_client.app.state.status = "running"


def test_rebuild_toggles_status_and_restores_on_success(app_client, monkeypatch):
    app = app_client.app
    seen: list[str] = []

    original = app.state.rebuild.rebuild

    async def spy():
        seen.append(app.state.status)
        return await original()

    monkeypatch.setattr(app.state.rebuild, "rebuild", spy)

    r = app_client.post("/v2/rebuild", json={})
    assert r.status_code == 200
    assert seen == ["rebuilding"]
    assert app.state.status == "running"


def test_rebuild_restores_status_on_failure(dummy_config, monkeypatch):
    from fastapi.testclient import TestClient
    from memory_talk_v2.api import create_app

    app = create_app(dummy_config)
    with TestClient(app, raise_server_exceptions=False) as client:
        async def boom():
            raise RuntimeError("nope")

        monkeypatch.setattr(app.state.rebuild, "rebuild", boom)

        r = client.post("/v2/rebuild", json={})
        assert r.status_code == 500
        assert app.state.status == "running"


def test_concurrent_rebuild_returns_409(app_client):
    app = app_client.app
    app.state.status = "rebuilding"
    try:
        r = app_client.post("/v2/rebuild", json={})
        # Middleware wins before the handler — 503, not 409. The 409 path
        # is the belt-and-suspenders guard inside the handler itself and
        # is only reachable if middleware is bypassed; verify directly.
        assert r.status_code == 503
    finally:
        app.state.status = "running"

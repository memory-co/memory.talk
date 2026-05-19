"""POST /v3/sync/{start,stop} + GET /v3/sync/status."""
from __future__ import annotations
import asyncio
import json

import httpx
import pytest

pytestmark = pytest.mark.asyncio


def _msg(uuid, parent, mtype, text, ts="2026-05-18T09:00:00Z", cwd="/work/proj"):
    return {
        "type": mtype, "uuid": uuid, "parentUuid": parent,
        "timestamp": ts, "isSidechain": False, "cwd": cwd,
        "message": {"role": mtype, "content": [{"type": "text", "text": text}]},
    }


@pytest.fixture
def fake_claude_root(tmp_path, monkeypatch):
    """Point ClaudeCodeAdapter at a tmp tree with one prepared session jsonl."""
    root = tmp_path / "fake_claude_projects"
    proj = root / "myproject"
    proj.mkdir(parents=True)
    f = proj / "abc-123.jsonl"
    f.write_text(
        json.dumps(_msg("u1", None, "user", "hello")) + "\n"
        + json.dumps(_msg("a1", "u1", "assistant", "hi back")) + "\n"
    )
    from memorytalk.adapters.claude_code import ClaudeCodeAdapter
    monkeypatch.setattr(ClaudeCodeAdapter, "DEFAULT_ROOT", root)
    return root, f


async def test_sync_start_backfills_existing_sessions(client, fake_claude_root):
    r = await client.post("/v3/sync/start")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "started"
    assert "claude-code" in body["adapters"]
    bf = body["backfill"]
    assert bf["discovered"] == 1
    assert bf["imported"] == 1
    r = await client.get("/v3/status")
    assert r.json()["sessions_total"] == 1


async def test_sync_already_running(client, fake_claude_root):
    await client.post("/v3/sync/start")
    r = await client.post("/v3/sync/start")
    assert r.json()["status"] == "already_running"


async def test_sync_stop_returns_totals(client, fake_claude_root):
    await client.post("/v3/sync/start")
    r = await client.post("/v3/sync/stop")
    body = r.json()
    assert body["status"] == "stopped"
    assert body["totals"]["imported"] == 1


async def test_sync_status_includes_last_run_after_stop(client, fake_claude_root):
    await client.post("/v3/sync/start")
    await client.post("/v3/sync/stop")
    r = await client.get("/v3/sync/status")
    body = r.json()
    assert body["status"] == "stopped"
    assert body["last_run"] is not None
    assert body["last_run"]["totals"]["imported"] == 1


async def test_sync_picks_up_appended_round(client, fake_claude_root):
    """Append a third message to the session file; watcher should detect
    it and `appended` should show up in the totals."""
    _, session_file = fake_claude_root
    await client.post("/v3/sync/start")
    r = await client.post("/v3/read", json={"id": "sess_abc-123"})
    assert len(r.json()["session"]["rounds"]) == 2

    with session_file.open("a") as f:
        f.write(json.dumps(_msg("u2", "a1", "user", "third question")) + "\n")

    for _ in range(20):
        await asyncio.sleep(0.2)
        r = await client.post("/v3/read", json={"id": "sess_abc-123"})
        if len(r.json()["session"]["rounds"]) == 3:
            break
    assert len(r.json()["session"]["rounds"]) == 3
    r = await client.get("/v3/sync/status")
    assert r.json()["totals"]["appended"] >= 1


async def test_sync_state_persists_across_app_restarts(data_root, fake_claude_root, monkeypatch):
    """`sync_state.json` flag survives a lifespan exit (which uses pause(),
    not stop(), so the explicit choice is preserved)."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(data_root))
    from memorytalk.api import create_app
    from memorytalk.config import Config

    app1 = create_app(Config())
    async with app1.router.lifespan_context(app1):
        t = httpx.ASGITransport(app=app1)
        async with httpx.AsyncClient(transport=t, base_url="http://t") as ac:
            await ac.post("/v3/sync/start")
            assert (await ac.get("/v3/status")).json()["sync_enabled"] is True

    flag = (data_root / "sync_state.json").read_text()
    assert "true" in flag

    app2 = create_app(Config())
    async with app2.router.lifespan_context(app2):
        t = httpx.ASGITransport(app=app2)
        async with httpx.AsyncClient(transport=t, base_url="http://t") as ac:
            assert (await ac.get("/v3/status")).json()["sync_enabled"] is True


async def test_sync_auto_resume_actually_runs_watcher(data_root, fake_claude_root, monkeypatch):
    """Gap fill: previous test only checked the persisted flag — this one
    confirms the watcher is *actually running* (status reports adapters +
    watching paths, not just sync_enabled=True at /status level)."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(data_root))
    from memorytalk.api import create_app
    from memorytalk.config import Config

    # Lifespan #1 — explicit sync start, persists the flag.
    app1 = create_app(Config())
    async with app1.router.lifespan_context(app1):
        t = httpx.ASGITransport(app=app1)
        async with httpx.AsyncClient(transport=t, base_url="http://t") as ac:
            await ac.post("/v3/sync/start")

    # Lifespan #2 — fresh app; should auto-resume so /v3/sync/status reports running.
    app2 = create_app(Config())
    async with app2.router.lifespan_context(app2):
        t = httpx.ASGITransport(app=app2)
        async with httpx.AsyncClient(transport=t, base_url="http://t") as ac:
            r = await ac.get("/v3/sync/status")
            body = r.json()
            assert body["status"] == "running", (
                "auto-resume should have started the watcher in lifespan #2"
            )
            assert "claude-code" in body["adapters"]
            # And the watcher's `watching` paths are real (or at least listed).
            assert len(body["watching"]) >= 1

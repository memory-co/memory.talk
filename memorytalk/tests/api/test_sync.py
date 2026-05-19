"""GET /v3/sync/status + lifespan auto-start driven by settings.

Sync no longer has a CLI/HTTP control plane — ``settings.sync.enabled``
is the switch and the lifespan reads it on every server (re)start.
"""
from __future__ import annotations
import asyncio
import json

import httpx
import pytest
import pytest_asyncio

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


@pytest.fixture
def sync_data_root(tmp_path, monkeypatch):
    """Like ``data_root`` but with ``sync.enabled=True`` so lifespan
    auto-starts the watcher."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
        "sync": {"enabled": True, "debounce_ms": 50},
    }))
    return tmp_path


@pytest_asyncio.fixture
async def sync_app(sync_data_root):
    """Lifespan-driven app. Note: any fixture that prepares adapter data
    (e.g. ``fake_claude_root``) must run BEFORE this fixture so the
    monkeypatch is in effect when lifespan kicks off the watcher. Use
    ``sync_client_with_claude`` below — or list adapter-data fixtures
    earlier than ``sync_client`` in the test signature."""
    from memorytalk.api import create_app
    from memorytalk.config import Config
    a = create_app(Config())
    async with a.router.lifespan_context(a):
        yield a


@pytest_asyncio.fixture
async def sync_client(sync_app):
    transport = httpx.ASGITransport(app=sync_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac


@pytest_asyncio.fixture
async def sync_client_with_claude(sync_data_root, fake_claude_root):
    """Composite fixture: ensures adapter data is staged + monkeypatched
    BEFORE lifespan boots so backfill sees the fake tree."""
    from memorytalk.api import create_app
    from memorytalk.config import Config
    a = create_app(Config())
    async with a.router.lifespan_context(a):
        transport = httpx.ASGITransport(app=a)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            yield ac


async def _wait_for_phase(client: httpx.AsyncClient, target: str, *, timeout=5.0):
    """Poll /v3/sync/status until ``phase == target``, then return body."""
    for _ in range(int(timeout / 0.05)):
        r = await client.get("/v3/sync/status")
        body = r.json()
        if body.get("phase") == target:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError(f"phase never reached {target!r}; last={body!r}")


# ────────── disabled / error states ──────────

async def test_status_disabled_when_settings_off(client):
    """Default fixture has sync.enabled=False — status reports `disabled`."""
    r = await client.get("/v3/sync/status")
    assert r.status_code == 200
    assert r.json() == {"status": "disabled"}


async def test_start_and_stop_routes_are_gone(client):
    """The old control plane no longer exists."""
    assert (await client.post("/v3/sync/start")).status_code in (404, 405)
    assert (await client.post("/v3/sync/stop")).status_code in (404, 405)


# ────────── enabled / backfill / live watch ──────────

async def test_lifespan_auto_starts_watcher_and_backfills(sync_client_with_claude):
    """sync.enabled=True → lifespan spins watcher up → backfill ingests
    the prepared session within a few hundred ms (in-process, dummy
    embedder, tiny payload)."""
    body = await _wait_for_phase(sync_client_with_claude, "watching")
    assert body["status"] == "running"
    assert "claude-code" in body["adapters"]
    r = await sync_client_with_claude.get("/v3/status")
    assert r.json()["sessions_total"] == 1


async def test_watcher_picks_up_appended_round(sync_client_with_claude, fake_claude_root):
    _, session_file = fake_claude_root
    await _wait_for_phase(sync_client_with_claude, "watching")

    r = await sync_client_with_claude.post("/v3/read", json={"id": "sess_abc-123"})
    assert len(r.json()["session"]["rounds"]) == 2

    with session_file.open("a") as f:
        f.write(json.dumps(_msg("u2", "a1", "user", "third question")) + "\n")

    for _ in range(20):
        await asyncio.sleep(0.2)
        r = await sync_client_with_claude.post("/v3/read", json={"id": "sess_abc-123"})
        if len(r.json()["session"]["rounds"]) == 3:
            break
    assert len(r.json()["session"]["rounds"]) == 3
    r = await sync_client_with_claude.get("/v3/sync/status")
    assert r.json()["totals"]["appended"] >= 1


# ────────── /v3/status field ──────────

async def test_v3_status_sync_enabled_reflects_settings(sync_client_with_claude):
    assert (await sync_client_with_claude.get("/v3/status")).json()["sync_enabled"] is True


# ────────── legacy sync_state.json migration ──────────

async def test_legacy_sync_state_migrates_into_settings(tmp_path, monkeypatch):
    """Pre-0.5 installs persisted enable in ``sync_state.json``. First
    Config() load after upgrade folds it into settings.sync.enabled and
    deletes the legacy file."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
        # NOTE: no `sync.enabled` field — simulates a settings.json that
        # predates this field.
        "sync": {"debounce_ms": 50},
    }))
    (tmp_path / "sync_state.json").write_text(json.dumps({"enabled": True}))

    from memorytalk.config import Config
    cfg = Config()
    assert cfg.settings.sync.enabled is True
    assert not (tmp_path / "sync_state.json").exists()
    # And the migration persisted the new value.
    merged = json.loads((tmp_path / "settings.json").read_text())
    assert merged["sync"]["enabled"] is True


async def test_legacy_sync_state_ignored_when_new_field_already_set(tmp_path, monkeypatch):
    """If settings.sync.enabled is already present (post-migration or
    post-setup), the legacy file is treated as stale and removed without
    overwriting the user's choice."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({
        "embedding": {"provider": "dummy", "dim": 384},
        "sync": {"enabled": False, "debounce_ms": 50},
    }))
    (tmp_path / "sync_state.json").write_text(json.dumps({"enabled": True}))

    from memorytalk.config import Config
    cfg = Config()
    assert cfg.settings.sync.enabled is False   # user choice wins
    assert not (tmp_path / "sync_state.json").exists()


# ────────── backfill error isolation ──────────

async def test_per_session_backfill_error_does_not_abort(sync_data_root, fake_claude_root, monkeypatch):
    """A poisoned adapter that raises mid-iter_sessions should be
    isolated — the per-adapter try/except in _run_backfill records the
    error and moves on."""
    from memorytalk.adapters import ADAPTERS
    from memorytalk.adapters.base import BaseAdapter

    class _PoisonAdapter(BaseAdapter):
        source_name = "poison"
        DEFAULT_ROOT = sync_data_root / "nowhere"

        def watch_roots(self):
            return []

        def iter_sessions(self):
            raise RuntimeError("boom")

        def convert_file(self, path):
            return None

    # Inject for one test only.
    monkeypatch.setitem(ADAPTERS, "poison", _PoisonAdapter)

    from memorytalk.api import create_app
    from memorytalk.config import Config
    a = create_app(Config())
    async with a.router.lifespan_context(a):
        transport = httpx.ASGITransport(app=a)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            body = await _wait_for_phase(ac, "watching")
            assert body["status"] == "running"
            # claude-code adapter should still have ingested its session
            assert (await ac.get("/v3/status")).json()["sessions_total"] == 1
            # The poison adapter's error should show up in recent.
            r = await ac.get("/v3/sync/status", params={"limit": 20})
            errs = [e for e in r.json()["recent"] if e.get("event") == "error"]
            assert any("boom" in (e.get("error") or "") for e in errs), errs

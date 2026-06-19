"""GET /v4/sync/status + lifespan auto-start driven by settings.

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
    """Point ClaudeCodeAdapter at a tmp tree with one prepared session jsonl.

    Returns ``(root, jsonl_path, minted_sid)``. The minted sid depends
    on (source, location) hash, so it must be computed after the
    monkeypatch points DEFAULT_LOCATION at the tmp tree.

    Also points the CodexAdapter at a nonexistent tmp path so the
    auto-detect loop in SyncWatcher doesn't pick up the developer's
    real ``~/.codex/sessions/`` data during a test run.
    """
    root = tmp_path / "fake_claude_projects"
    proj = root / "myproject"
    proj.mkdir(parents=True)
    f = proj / "abc-123.jsonl"
    f.write_text(
        json.dumps(_msg("u1", None, "user", "hello")) + "\n"
        + json.dumps(_msg("a1", "u1", "assistant", "hi back")) + "\n"
    )
    from memorytalk.adapters.claude_code import ClaudeCodeAdapter
    from memorytalk.adapters.codex import CodexAdapter
    monkeypatch.setattr(ClaudeCodeAdapter, "DEFAULT_LOCATION", str(root))
    monkeypatch.setattr(
        CodexAdapter, "DEFAULT_LOCATION", str(tmp_path / "no_codex_here"),
    )
    sid = ClaudeCodeAdapter(location=str(root)).mint_session_id("abc-123")
    return root, f, sid


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
    """Poll /v4/sync/status until ``phase == target``, then return body."""
    for _ in range(int(timeout / 0.05)):
        r = await client.get("/v4/sync/status")
        body = r.json()
        if body.get("phase") == target:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError(f"phase never reached {target!r}; last={body!r}")


# ────────── disabled / error states ──────────

async def test_status_disabled_when_settings_off(client):
    """Default fixture has sync.enabled=False — status reports `disabled`."""
    r = await client.get("/v4/sync/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "disabled"
    # Index health is reported even when sync is off — it's a property
    # of the data root, not the watcher.
    assert "index" in body
    assert body["index"]["total_sessions"] == 0
    assert body["index"]["degraded_sessions"] == 0


async def test_start_and_stop_routes_are_gone(client):
    """The old control plane no longer exists."""
    assert (await client.post("/v4/sync/start")).status_code in (404, 405)
    assert (await client.post("/v4/sync/stop")).status_code in (404, 405)


# ────────── enabled / backfill / live watch ──────────

async def test_lifespan_auto_starts_watcher_and_backfills(sync_client_with_claude):
    """sync.enabled=True → lifespan spins watcher up → backfill ingests
    the prepared session within a few hundred ms (in-process, dummy
    embedder, tiny payload)."""
    body = await _wait_for_phase(sync_client_with_claude, "watching")
    assert body["status"] == "running"
    assert "claude-code" in body["adapters"]
    r = await sync_client_with_claude.get("/v4/status")
    assert r.json()["sessions_total"] == 1


async def test_watcher_logs_lifecycle_and_events(sync_client_with_claude, fake_claude_root, caplog):
    """The `memorytalk.sync.watch` logger emits at every major transition:
    watcher start, backfill milestones, file events received, ingest
    outcomes. The dictConfig that routes these to ``logs/sync/watch.log``
    is the daemon shim's job — here we just verify the call sites fire."""
    _, session_file, sid = fake_claude_root
    caplog.set_level("INFO", logger="memorytalk.sync.watch")
    await _wait_for_phase(sync_client_with_claude, "watching")

    # Trigger a fresh file event so on_event/_worker_loop log paths run.
    with session_file.open("a") as f:
        f.write(json.dumps(_msg("u9", "a1", "user", "another round")) + "\n")
    for _ in range(20):
        await asyncio.sleep(0.2)
        r = await sync_client_with_claude.post("/v4/read", json={"id": sid})
        if len(r.json()["session"]["rounds"]) == 3:
            break

    records = [r.getMessage() for r in caplog.records
               if r.name == "memorytalk.sync.watch"]
    joined = "\n".join(records)
    # Note: ``watcher started`` is logged during lifespan startup which
    # runs in the fixture *before* caplog activates — so it won't appear
    # in records. We still see the backfill / event / ingest lines
    # because those fire during the test body.
    assert "backfill finished" in joined, joined
    assert any("event adapter=claude-code" in m for m in records), joined
    # 0.7.x: ingested log line now keys on endpoint=<source@label>, not adapter=<source>.
    assert any("ingested endpoint=claude-code" in m for m in records), joined


async def test_watcher_picks_up_appended_round(sync_client_with_claude, fake_claude_root):
    _, session_file, sid = fake_claude_root
    await _wait_for_phase(sync_client_with_claude, "watching")

    r = await sync_client_with_claude.post("/v4/read", json={"id": sid})
    assert len(r.json()["session"]["rounds"]) == 2

    with session_file.open("a") as f:
        f.write(json.dumps(_msg("u2", "a1", "user", "third question")) + "\n")

    for _ in range(20):
        await asyncio.sleep(0.2)
        r = await sync_client_with_claude.post("/v4/read", json={"id": sid})
        if len(r.json()["session"]["rounds"]) == 3:
            break
    assert len(r.json()["session"]["rounds"]) == 3
    r = await sync_client_with_claude.get("/v4/sync/status")
    assert r.json()["totals"]["appended"] >= 1


# ────────── /v4/status field ──────────

async def test_v3_status_sync_enabled_reflects_settings(sync_client_with_claude):
    assert (await sync_client_with_claude.get("/v4/status")).json()["sync_enabled"] is True


# ────────── per-endpoint visibility (0.7.x) ──────────

async def test_status_surfaces_endpoint_breakdown(sync_client_with_claude):
    """``GET /v4/sync/status`` carries per-endpoint counters and an
    endpoints list, so the CLI / consumers can render a one-row-per-source
    view without re-aggregating client-side."""
    body = await _wait_for_phase(sync_client_with_claude, "watching")
    # endpoints reflects what the watcher built from settings/auto-detect.
    eps = body.get("endpoints") or []
    assert any(e["source"] == "claude-code" for e in eps)
    # The per-endpoint slice mirrors totals[claude-code@<label>] — same
    # counter shape.
    by_ep = body.get("totals_by_endpoint") or {}
    cc_key = next((k for k in by_ep if k.startswith("claude-code@")), None)
    assert cc_key is not None, by_ep
    cc_totals = by_ep[cc_key]
    # Index health by endpoint surfaces the data-completeness picture.
    by_endpoint_idx = (body.get("index") or {}).get("by_endpoint") or []
    cc_idx = next(
        (r for r in by_endpoint_idx if r["source"] == "claude-code"), None,
    )
    assert cc_idx is not None
    assert cc_idx["sessions"] == 1
    assert cc_idx["rounds"] >= 2
    # Imported should match the index — every session backfilled should
    # have bumped imported by 1 in the per-endpoint totals.
    assert cc_totals["imported"] >= 1


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
        # Must be an existing path: auto-detect skips adapters whose
        # DEFAULT_LOCATION doesn't exist on disk. sync_data_root is the
        # data dir created by the fixture, guaranteed to exist.
        DEFAULT_LOCATION = str(sync_data_root)

        def watch_roots(self):
            return []

        def list_sources(self):
            raise RuntimeError("boom")

        def probe(self, source_id):
            return None

        def read_after(self, source_id, after_round_id, hint_line_offset=0):
            raise RuntimeError("unreachable")

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
            assert (await ac.get("/v4/status")).json()["sessions_total"] == 1
            # The poison adapter's error should show up in recent.
            r = await ac.get("/v4/sync/status", params={"limit": 20})
            errs = [e for e in r.json()["recent"] if e.get("event") == "error"]
            assert any("boom" in (e.get("error") or "") for e in errs), errs

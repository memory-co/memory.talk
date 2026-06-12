"""End-to-end: seed a data_root with 0.8.1-shaped state, boot the
v3 app via the real lifespan, then exercise the app to prove the
upgrade was seamless.

This is the load-bearing test for the user's directive — a 0.8.1
install must boot on the current code without manual intervention.
"""
from __future__ import annotations

import json
from pathlib import Path

import aiosqlite
import httpx
import pyarrow as pa
import pytest


# ─── 0.8.1 seed helpers ────────────────────────────────────────────


_SETTINGS_JSON = {
    "embedding": {"provider": "dummy", "dim": 384},
    "sync": {"debounce_ms": 50, "enabled": False},
    "index": {"lance_flush_rows": 1, "lance_flush_interval_seconds": 0},
}


async def _seed_081_sqlite(db_path: Path) -> None:
    """Write a memory.db with the 0.8.1 schema (missing several
    columns we added in 0.8.x → 0.9 and carrying the legacy tables)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(db_path))
    try:
        await conn.execute(
            "CREATE TABLE sessions ("
            "  session_id TEXT PRIMARY KEY, source TEXT NOT NULL,"
            "  cwd TEXT, created_at TEXT NOT NULL, synced_at TEXT NOT NULL,"
            "  metadata TEXT NOT NULL DEFAULT '{}',"
            "  round_count INTEGER NOT NULL DEFAULT 0)"
        )
        await conn.execute(
            "CREATE TABLE cards (card_id TEXT PRIMARY KEY,"
            " insight TEXT NOT NULL, rounds TEXT NOT NULL DEFAULT '[]',"
            " created_at TEXT NOT NULL)"
        )
        await conn.execute(
            "CREATE TABLE card_stats ("
            "  card_id TEXT PRIMARY KEY, review_up INT DEFAULT 0,"
            "  review_down INT DEFAULT 0, review_neutral INT DEFAULT 0,"
            "  review_count INT DEFAULT 0, read_count INT DEFAULT 0,"
            "  recall_count INT DEFAULT 0,"
            "  updated_at TEXT NOT NULL)"
        )
        await conn.execute(
            "CREATE TABLE recall_log (id TEXT PRIMARY KEY,"
            " session_id TEXT, ts TEXT)"
        )
        await conn.execute(
            "CREATE TABLE rounds_index ("
            "  session_id TEXT, idx INT, round_id TEXT)"
        )
        await conn.execute(
            "INSERT INTO sessions VALUES('s1','claude-code','/x',"
            "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','{}',2)"
        )
        await conn.execute("INSERT INTO rounds_index VALUES('s1',1,'r1')")
        await conn.execute("INSERT INTO rounds_index VALUES('s1',2,'r2')")
        await conn.execute(
            "INSERT INTO cards VALUES('c1','hello insight','[]','2026-01-01T00:00:00Z')"
        )
        await conn.commit()
    finally:
        await conn.close()


async def _seed_081_lancedb(vectors_dir: Path, dim: int = 384) -> None:
    """Write a LanceDB at ``vectors_dir`` with the 0.8.1 cards + rounds
    tables (``card_id`` instead of ``id``, no ``_base_id`` / ``_chunk``).
    The tables are empty — we only care that the columns get migrated;
    the search hot path is exercised by other tests."""
    import lancedb

    vectors_dir.mkdir(parents=True, exist_ok=True)
    db = await lancedb.connect_async(str(vectors_dir))
    cards_schema = pa.schema([
        pa.field("card_id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), dim)),
    ])
    rounds_schema = pa.schema([
        pa.field("session_id", pa.string()),
        pa.field("idx", pa.int32()),
        pa.field("role", pa.string()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), dim)),
    ])
    await db.create_table("cards", schema=cards_schema)
    await db.create_table("rounds", schema=rounds_schema)


# ─── tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_081_data_root_boots_cleanly_and_serves_status(
    tmp_path, monkeypatch,
):
    """Seed a 0.8.1-shaped data_root, boot the app, hit /v3/status —
    no crash, no SystemExit, and the v3 schema is now in place."""
    (tmp_path / "settings.json").write_text(json.dumps(_SETTINGS_JSON))
    await _seed_081_sqlite(tmp_path / "memory.db")
    await _seed_081_lancedb(tmp_path / "vectors")

    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    from memorytalk.api import create_app
    from memorytalk.config import Config

    app = create_app(Config())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t",
        ) as client:
            resp = await client.get("/v3/status")
            assert resp.status_code == 200

        # State file got written by the runner; check we recorded both
        # subsystems at v1.
        state_path = tmp_path / "migrations_state.json"
        assert state_path.exists()
        body = json.loads(state_path.read_text())
        applied = {(a["version"], a["subsystem"]) for a in body["applied"]}
        assert ("v1", "database") in applied
        assert ("v1", "searchbase") in applied

        # And the database now has the v1 shape — quick spot check.
        conn = await aiosqlite.connect(str(tmp_path / "memory.db"))
        try:
            async with conn.execute("PRAGMA table_info(sessions)") as cur:
                cols = {r[1] for r in await cur.fetchall()}
            assert "tags" in cols
            assert "last_round_id" in cols
            async with conn.execute(
                "SELECT last_round_id FROM sessions WHERE session_id='s1'"
            ) as cur:
                assert (await cur.fetchone())[0] == "r2"
            async with conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='recall_log'"
            ) as cur:
                assert await cur.fetchone() is None
        finally:
            await conn.close()


@pytest.mark.asyncio
async def test_fresh_install_marks_v1_for_both_subsystems(
    tmp_path, monkeypatch,
):
    """Empty data_root → init_latest path. After boot, the state file
    should record v1 applied for both subsystems so the next boot is a
    no-op."""
    (tmp_path / "settings.json").write_text(json.dumps(_SETTINGS_JSON))
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))

    from memorytalk.api import create_app
    from memorytalk.config import Config

    app = create_app(Config())
    async with app.router.lifespan_context(app):
        body = json.loads(
            (tmp_path / "migrations_state.json").read_text()
        )
        applied = {(a["version"], a["subsystem"]) for a in body["applied"]}
        assert ("v1", "database") in applied
        assert ("v1", "searchbase") in applied
        # Methods should be init, not up — this was a clean install.
        for row in body["applied"]:
            assert row["method"] == "init"


@pytest.mark.asyncio
async def test_second_boot_is_noop(tmp_path, monkeypatch):
    """Boot twice. The second boot must add nothing to the state file."""
    (tmp_path / "settings.json").write_text(json.dumps(_SETTINGS_JSON))
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))

    from memorytalk.api import create_app
    from memorytalk.config import Config

    app1 = create_app(Config())
    async with app1.router.lifespan_context(app1):
        pass
    first = json.loads((tmp_path / "migrations_state.json").read_text())

    app2 = create_app(Config())
    async with app2.router.lifespan_context(app2):
        pass
    second = json.loads((tmp_path / "migrations_state.json").read_text())

    # Same set of applied rows.
    s1 = {(a["version"], a["subsystem"]) for a in first["applied"]}
    s2 = {(a["version"], a["subsystem"]) for a in second["applied"]}
    assert s1 == s2

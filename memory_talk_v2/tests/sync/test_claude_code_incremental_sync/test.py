"""Incremental sync scenario — drives the real CLI across platform growth.

Phase 1: CLI sync from platform_initial/   — fresh import
Phase 2: CLI sync from platform_initial/   — same bytes, sha256 fast-path → skipped
Phase 3: CLI sync from platform_grown/     — new rounds append to session
Phase 4: CLI sync from platform_grown/     — same grown bytes → skipped

Each phase asserts the CLI summary JSON (imported/appended/skipped counts).
The `expected/` fixtures capture the END-OF-PHASE-3 state.

httpx is ASGI-routed into the in-process app (see tests/sync/conftest.py);
the full Click → httpx → FastAPI → service → SQLite/LanceDB/file stack
runs for real with no subprocess.

Regenerate: `REGENERATE_SYNC_FIXTURES=1 pytest memory_talk_v2/tests/sync/`
after an intentional adapter/schema change.
"""
from __future__ import annotations
import json
import os
from pathlib import Path


HERE = Path(__file__).parent
PLATFORM_INITIAL = HERE / "platform_initial"
PLATFORM_GROWN = HERE / "platform_grown"
EXPECTED_ROOT = HERE / "expected"
SESSIONS_ROOT = EXPECTED_ROOT / "sessions"
SQLITE_ROOT = EXPECTED_ROOT / "sqlite"

REGENERATE = os.environ.get("REGENERATE_SYNC_FIXTURES") == "1"

META_STRIP = {"synced_at"}
META_METADATA_STRIP = {"path"}
EVENT_STRIP = {"event_id", "at"}
TABLE_STRIP = {"sessions": {"synced_at"}, "rounds": set()}
JSON_COLS = {"sessions": ["metadata", "tags"], "rounds": ["content", "usage"]}
TABLES = ["sessions", "rounds"]


def _pk_cols(table: str) -> list[str]:
    return {"sessions": ["session_id"], "rounds": ["session_id", "idx"]}[table]


def _dump_table(db, table: str) -> list[dict]:
    rows = db.conn.execute(
        f"SELECT * FROM {table} ORDER BY " + ",".join(_pk_cols(table))
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for col in JSON_COLS.get(table, []):
            if d.get(col) is not None:
                d[col] = json.loads(d[col])
        for col in TABLE_STRIP.get(table, set()):
            d.pop(col, None)
        if table == "sessions" and isinstance(d.get("metadata"), dict):
            for k in META_METADATA_STRIP:
                d["metadata"].pop(k, None)
        out.append(d)
    return out


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _strip_events(events: list[dict]) -> list[dict]:
    return [{k: v for k, v in e.items() if k not in EVENT_STRIP} for e in events]


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _strip_meta(meta: dict) -> dict:
    out = {k: v for k, v in meta.items() if k not in META_STRIP}
    if isinstance(out.get("metadata"), dict):
        out["metadata"] = {k: v for k, v in out["metadata"].items() if k not in META_METADATA_STRIP}
    return out


def _run_sync(cli_env, platform: Path) -> dict:
    result = cli_env.runner.invoke(cli_env.main, [
        "sync",
        "--source=claude-code",
        "--platform-root", str(platform),
        "--data-root", str(cli_env.config.data_root),
    ])
    assert result.exit_code == 0, f"CLI exited {result.exit_code}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    return json.loads(result.stdout)


def test_claude_code_incremental_sync(cli_env):
    # Phase 1: seed import
    assert _run_sync(cli_env, PLATFORM_INITIAL) == {
        "status": "ok",
        "imported": 1, "appended": 0, "skipped": 0, "partial_append": 0,
        "errors": [],
    }

    # Phase 2: same bytes → skipped
    assert _run_sync(cli_env, PLATFORM_INITIAL) == {
        "status": "ok",
        "imported": 0, "appended": 0, "skipped": 1, "partial_append": 0,
        "errors": [],
    }

    # Phase 3: grown bytes → 2 new rounds appended
    assert _run_sync(cli_env, PLATFORM_GROWN) == {
        "status": "ok",
        "imported": 0, "appended": 1, "skipped": 0, "partial_append": 0,
        "errors": [],
    }

    # Phase 4: grown bytes again → skipped
    assert _run_sync(cli_env, PLATFORM_GROWN) == {
        "status": "ok",
        "imported": 0, "appended": 0, "skipped": 1, "partial_append": 0,
        "errors": [],
    }

    # --- end-of-phase-3 snapshot comparison ---
    raw_session_id = "01K3A2BRG5N9F4YXH8MKPW6D7Q"
    session_id = f"sess_{raw_session_id}"
    bucket = raw_session_id[:2].lower()
    config = cli_env.config
    actual_session_dir = config.sessions_dir / "claude-code" / bucket / session_id
    actual_meta = _strip_meta(json.loads((actual_session_dir / "meta.json").read_text(encoding="utf-8")))
    actual_rounds = _read_jsonl(actual_session_dir / "rounds.jsonl")
    actual_events = _strip_events(_read_jsonl(actual_session_dir / "events.jsonl"))

    db = cli_env.app.state.db
    actual_tables = {t: _dump_table(db, t) for t in TABLES}

    expected_session_dir = SESSIONS_ROOT / "claude-code" / bucket / session_id

    if REGENERATE:
        _write_json(expected_session_dir / "meta.json", actual_meta)
        _write_jsonl(expected_session_dir / "rounds.jsonl", actual_rounds)
        _write_jsonl(expected_session_dir / "events.jsonl", actual_events)
        for t in TABLES:
            _write_json(SQLITE_ROOT / f"{t}.json", actual_tables[t])
        raise RuntimeError(
            "REGENERATE_SYNC_FIXTURES=1: wrote fixtures, unset and re-run to assert"
        )

    expected_meta = json.loads((expected_session_dir / "meta.json").read_text(encoding="utf-8"))
    expected_rounds = _read_jsonl(expected_session_dir / "rounds.jsonl")
    expected_events = _read_jsonl(expected_session_dir / "events.jsonl")

    assert actual_meta == expected_meta, "meta.json diff"
    assert actual_rounds == expected_rounds, "rounds.jsonl diff"
    assert actual_events == expected_events, "events.jsonl diff"

    for t in TABLES:
        expected_rows = json.loads((SQLITE_ROOT / f"{t}.json").read_text(encoding="utf-8"))
        assert actual_tables[t] == expected_rows, f"SQLite table {t!r} diff"

    # Key invariant: rounds.jsonl is append-only.
    assert [r["idx"] for r in actual_rounds] == [1, 2, 3, 4]
    assert [r["round_id"] for r in actual_rounds] == ["b1", "b2", "b3", "b4"]

"""Full sync scenario — drives the real memory-talk CLI end-to-end.

`cli_env.runner.invoke(main, ["sync", ...,
        "--json",
    ])` runs the real Click CLI. The
CLI's httpx calls are routed through `httpx.ASGITransport(app=app)` so they
hit the in-process FastAPI app without binding a TCP port. Every line of
CLI code (arg parsing, adapter dispatch, counts aggregation, error
collection, JSON output), HTTP serialization, FastAPI routing, service
layer, SQLite, LanceDB and the file layout get exercised for real.

Covers the fresh-import path only. Re-sync with unchanged bytes asserts
sha256 fast-path (skipped). The incremental / append case lives in its own
sibling scenario (test_claude_code_incremental_sync/).

Compares real outputs against committed fixtures under `expected/`:
- `expected/sessions/<source>/<bucket>/<session_id>/meta.json`
- `expected/sessions/<source>/<bucket>/<session_id>/rounds.jsonl`
- `expected/sessions/<source>/<bucket>/<session_id>/events.jsonl`
- `expected/sqlite/<table>.json`

Non-deterministic fields (timestamps, random event_ids, absolute fixture
path captured into `metadata.path`) are stripped before diff.

Regenerate: `REGENERATE_SYNC_FIXTURES=1 pytest memory_talk_v2/tests/sync/`
after an intentional adapter/schema change.
"""
from __future__ import annotations
import json
import os
from pathlib import Path


HERE = Path(__file__).parent
PLATFORM = HERE / "platform"
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


async def _dump_table(db, table: str) -> list[dict]:
    async with db.conn.execute(
        f"SELECT * FROM {table} ORDER BY " + ",".join(_pk_cols(table))
    ) as cursor:
        rows = await cursor.fetchall()
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


def _run_sync(cli_env) -> dict:
    """Invoke `memory-talk sync ...` and parse the JSON summary output."""
    result = cli_env.runner.invoke(cli_env.main, [
        "sync",
        "--source=claude-code",
        "--platform-root", str(PLATFORM),
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, f"CLI exited {result.exit_code}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    return json.loads(result.stdout)


async def test_claude_code_full_sync(cli_env):
    summary = _run_sync(cli_env)
    assert summary == {
        "status": "ok",
        "imported": 1, "appended": 0, "skipped": 0, "partial_append": 0,
        "errors": [],
    }

    summary_again = _run_sync(cli_env)
    assert summary_again == {
        "status": "ok",
        "imported": 0, "appended": 0, "skipped": 1, "partial_append": 0,
        "errors": [],
    }

    raw_session_id = "01K2FZQE4XGKV7J9MBN8PYRD3A"
    session_id = f"sess_{raw_session_id}"
    bucket = raw_session_id[:2].lower()
    config = cli_env.config
    actual_session_dir = config.sessions_dir / "claude-code" / bucket / session_id
    actual_meta = _strip_meta(json.loads((actual_session_dir / "meta.json").read_text(encoding="utf-8")))
    actual_rounds = _read_jsonl(actual_session_dir / "rounds.jsonl")
    actual_events = _strip_events(_read_jsonl(actual_session_dir / "events.jsonl"))

    db = cli_env.app.state.db
    actual_tables = {t: await _dump_table(db, t) for t in TABLES}

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

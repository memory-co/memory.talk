"""Sync scenario: claude-code JSONL → adapter → /v2/sessions → file + SQLite.

Compares real outputs against committed fixtures under `expected/`:
- `expected/sessions/<source>/<bucket>/<session_id>/meta.json`      — meta
- `expected/sessions/<source>/<bucket>/<session_id>/rounds.jsonl`   — rounds
- `expected/sessions/<source>/<bucket>/<session_id>/events.jsonl`   — the session's event stream (file-resident in v2)
- `expected/sqlite/<table>.json`                                    — SQLite rows per populated table (no event_log — it's a file, not a table)

Non-deterministic fields (timestamps, random event_ids, the absolute path
captured into `metadata.path`) are stripped from the actual data before
diff; the committed fixtures do not contain those fields.

Regenerate: `REGENERATE_SYNC_FIXTURES=1 pytest memory_talk_v2/tests/sync/`
after an intentional adapter or schema change.
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

# Non-deterministic fields to drop before diff
META_STRIP = {"synced_at"}
META_METADATA_STRIP = {"path"}   # absolute fs path to the fixture jsonl
EVENT_STRIP = {"event_id", "at"}
TABLE_STRIP = {
    "sessions":   {"synced_at"},
    "rounds":     set(),
}
# Which columns are JSON-encoded in SQLite and need parsing for diff
JSON_COLS = {
    "sessions":   ["metadata", "tags"],
    "rounds":     ["content", "usage"],
}
# SQLite tables we snapshot (event_log is gone — events live per-object)
TABLES = ["sessions", "rounds"]


def _pk_cols(table: str) -> list[str]:
    return {
        "sessions": ["session_id"],
        "rounds":   ["session_id", "idx"],
    }[table]


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


def test_claude_code_sync(app_client):
    from memory_talk_v2.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter()
    actions = []
    for payload in adapter.iter_sessions(PLATFORM):
        r = app_client.post("/v2/sessions", json=payload)
        assert r.status_code == 200, r.text
        actions.append(r.json())

    assert len(actions) == 1
    session_id = actions[0]["session_id"]
    assert actions[0]["action"] == "imported"

    config = app_client.app.state.config
    bucket = session_id[len("sess_"):len("sess_")+2].lower()
    actual_session_dir = config.sessions_dir / "claude-code" / bucket / session_id
    actual_meta = _strip_meta(json.loads((actual_session_dir / "meta.json").read_text(encoding="utf-8")))
    actual_rounds = _read_jsonl(actual_session_dir / "rounds.jsonl")
    actual_events = _strip_events(_read_jsonl(actual_session_dir / "events.jsonl"))

    db = app_client.app.state.db
    actual_tables = {t: _dump_table(db, t) for t in TABLES}

    expected_session_rel = Path("claude-code") / bucket / session_id
    expected_session_dir = SESSIONS_ROOT / expected_session_rel

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

    # Idempotency: second run with unchanged bytes → skipped, no new rows/events
    for payload in adapter.iter_sessions(PLATFORM):
        r = app_client.post("/v2/sessions", json=payload)
        assert r.json()["action"] == "skipped"
    for t in TABLES:
        assert _dump_table(db, t) == actual_tables[t], f"idempotency broken for {t!r}"
    assert _strip_events(_read_jsonl(actual_session_dir / "events.jsonl")) == actual_events, \
        "idempotency broken for events.jsonl"

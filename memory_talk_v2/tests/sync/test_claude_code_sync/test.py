"""Sync scenario: claude-code JSONL → adapter → /v2/sessions → file + SQLite.

Compares real outputs against committed fixtures under `expected/`:
- `expected/sessions/<source>/<bucket>/<session_id>/meta.json` + `rounds.jsonl`
  — the v2 source-of-truth file layer
- `expected/sqlite/<table>.json` — a list of rows dumped from SQLite

Non-deterministic fields (timestamps, random event_ids, the absolute path
captured into `metadata.path`) are stripped from the actual data before
diff; the committed fixtures do not contain those fields.

Regenerate mode: set `REGENERATE_SYNC_FIXTURES=1` to overwrite the
`expected/` tree with the current actual output. Use after intentional
adapter/schema changes.
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
TABLE_STRIP = {
    "sessions":   {"synced_at"},
    "rounds":     set(),
    "event_log":  {"event_id", "at"},
    "ingest_log": {"synced_at", "sha256"},
}
# Which columns are JSON-encoded in SQLite and need to be parsed for diff
JSON_COLS = {
    "sessions":   ["metadata", "tags"],
    "rounds":     ["content", "usage"],
    "event_log":  ["detail"],
    "ingest_log": [],
}
# Which tables we snapshot
TABLES = ["sessions", "rounds", "event_log", "ingest_log"]


def _dump_table(db, table: str) -> list[dict]:
    rows = db.conn.execute(
        f"SELECT * FROM {table} ORDER BY "
        + (",".join(_pk_cols(table)))
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for col in JSON_COLS.get(table, []):
            if d.get(col) is not None:
                d[col] = json.loads(d[col])
        for col in TABLE_STRIP.get(table, set()):
            d.pop(col, None)
        # sessions.metadata may carry the absolute fixture path
        if table == "sessions" and isinstance(d.get("metadata"), dict):
            for k in META_METADATA_STRIP:
                d["metadata"].pop(k, None)
        out.append(d)
    return out


def _pk_cols(table: str) -> list[str]:
    return {
        "sessions":   ["session_id"],
        "rounds":     ["session_id", "idx"],
        "event_log":  ["at", "event_id"],
        "ingest_log": ["session_id", "sha256"],
    }[table]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


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

    # Run the full sync
    adapter = ClaudeCodeAdapter()
    actions = []
    for payload in adapter.iter_sessions(PLATFORM):
        r = app_client.post("/v2/sessions", json=payload)
        assert r.status_code == 200, r.text
        actions.append(r.json())

    assert len(actions) == 1
    session_id = actions[0]["session_id"]
    assert actions[0]["action"] == "imported"

    # ---- file layer: meta.json + rounds.jsonl ----
    config = app_client.app.state.config
    actual_session_dir = config.sessions_dir / "claude-code" / session_id[len("sess_"):len("sess_")+2].lower() / session_id
    actual_meta = _strip_meta(json.loads((actual_session_dir / "meta.json").read_text(encoding="utf-8")))
    actual_rounds = _read_jsonl(actual_session_dir / "rounds.jsonl")

    # ---- SQLite tables ----
    db = app_client.app.state.db
    actual_tables = {t: _dump_table(db, t) for t in TABLES}

    # Fixture paths
    expected_session_rel = Path("claude-code") / session_id[len("sess_"):len("sess_")+2].lower() / session_id
    expected_meta_path = SESSIONS_ROOT / expected_session_rel / "meta.json"
    expected_rounds_path = SESSIONS_ROOT / expected_session_rel / "rounds.jsonl"

    if REGENERATE:
        _write_json(expected_meta_path, actual_meta)
        _write_jsonl(expected_rounds_path, actual_rounds)
        for t in TABLES:
            _write_json(SQLITE_ROOT / f"{t}.json", actual_tables[t])
        # Force a failure so CI notices — never leave regeneration mode as green.
        raise RuntimeError(
            "REGENERATE_SYNC_FIXTURES=1: wrote fixtures, unset and re-run to assert"
        )

    expected_meta = json.loads(expected_meta_path.read_text(encoding="utf-8"))
    expected_rounds = _read_jsonl(expected_rounds_path)

    assert actual_meta == expected_meta, "meta.json diff"
    assert actual_rounds == expected_rounds, "rounds.jsonl diff"

    for t in TABLES:
        expected_rows = json.loads((SQLITE_ROOT / f"{t}.json").read_text(encoding="utf-8"))
        assert actual_tables[t] == expected_rows, f"SQLite table {t!r} diff"

    # Idempotency: second run with unchanged bytes → skipped, no new rows
    for payload in adapter.iter_sessions(PLATFORM):
        r = app_client.post("/v2/sessions", json=payload)
        assert r.json()["action"] == "skipped"
    for t in TABLES:
        again = _dump_table(db, t)
        assert again == actual_tables[t], f"idempotency broken for {t!r}"

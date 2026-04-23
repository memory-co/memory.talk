"""Incremental sync scenario: existing session grows, new rounds get appended.

Phase 1 (seed) — adapter ingests `platform_initial/`, server stores it.
Phase 2 (unchanged) — same bytes: sha256 fast-path → action=skipped.
Phase 3 (grown)   — adapter ingests `platform_grown/` (same session_id,
                    new rounds appended to the raw jsonl): server detects
                    round_id mismatch on the new rounds, appends them
                    with continuing idx, emits a rounds_appended event.
Phase 4 (stable)  — same grown bytes again: action=skipped.

The `expected/` fixtures capture the END-OF-PHASE-3 state — rounds.jsonl
has all rounds (initial + new), events.jsonl has imported + rounds_appended,
meta.json shows the grown round_count and the grown last_sha256.

This scenario is fully isolated from test_claude_code_full_sync/ — they
share no fixtures or data. Each uses its own `app_client` (fresh
tmp_data_root via pytest fixtures), so there is no cross-test leakage.

Regenerate: `REGENERATE_SYNC_FIXTURES=1 pytest
memory_talk_v2/tests/sync/test_claude_code_incremental_sync/`
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


def _sync_once(platform: Path, app_client):
    from memory_talk_v2.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter()
    actions = []
    for payload in adapter.iter_sessions(platform):
        r = app_client.post("/v2/sessions", json=payload)
        assert r.status_code == 200, r.text
        actions.append(r.json())
    return actions


def test_claude_code_incremental_sync(app_client):
    # Phase 1: seed import
    actions1 = _sync_once(PLATFORM_INITIAL, app_client)
    assert len(actions1) == 1
    assert actions1[0]["action"] == "imported"
    assert actions1[0]["round_count"] == 2
    assert actions1[0]["added_count"] == 2
    session_id = actions1[0]["session_id"]

    # Phase 2: same bytes again → skipped
    actions2 = _sync_once(PLATFORM_INITIAL, app_client)
    assert actions2[0]["action"] == "skipped"

    # Phase 3: platform file grew by 2 rounds → appended
    actions3 = _sync_once(PLATFORM_GROWN, app_client)
    assert len(actions3) == 1
    assert actions3[0]["session_id"] == session_id
    assert actions3[0]["action"] == "appended"
    assert actions3[0]["added_count"] == 2
    assert actions3[0]["round_count"] == 4
    assert actions3[0]["overwrite_skipped"] == []

    # Phase 4: same grown bytes again → skipped
    actions4 = _sync_once(PLATFORM_GROWN, app_client)
    assert actions4[0]["action"] == "skipped"

    # ---- snapshot comparison: post-phase-3 state ----
    config = app_client.app.state.config
    bucket = session_id[len("sess_"):len("sess_") + 2].lower()
    actual_session_dir = config.sessions_dir / "claude-code" / bucket / session_id
    actual_meta = _strip_meta(json.loads((actual_session_dir / "meta.json").read_text(encoding="utf-8")))
    actual_rounds = _read_jsonl(actual_session_dir / "rounds.jsonl")
    actual_events = _strip_events(_read_jsonl(actual_session_dir / "events.jsonl"))

    db = app_client.app.state.db
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

    # Key invariant: rounds.jsonl is append-only. The first 2 lines (seed rounds)
    # must be byte-identical to what phase 1 wrote — overwrite-detection and
    # replay safety depend on it.
    assert [r["idx"] for r in actual_rounds] == [1, 2, 3, 4]
    assert [r["round_id"] for r in actual_rounds] == ["b1", "b2", "b3", "b4"]

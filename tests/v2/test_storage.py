import sqlite3
from memory_talk.v2.storage.schema import init_v2_schema


def test_init_creates_search_log_table(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_v2_schema(conn)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_log'").fetchall()
    assert len(rows) == 1


def test_search_log_columns(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_v2_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(search_log)")}
    assert cols == {"search_id", "query", "where_dsl", "top_k", "created_at", "response_json"}


def test_init_creates_event_log_table(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_v2_schema(conn)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event_log'").fetchall()
    assert len(rows) == 1


def test_event_log_columns(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_v2_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(event_log)")}
    assert cols == {"event_id", "object_id", "object_kind", "at", "kind", "detail_json"}


def test_init_is_idempotent(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_v2_schema(conn)
    init_v2_schema(conn)  # should not raise
    rows = conn.execute("SELECT COUNT(*) FROM search_log").fetchone()
    assert rows[0] == 0

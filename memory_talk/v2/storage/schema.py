"""v2 SQLite schema additions (search_log, event_log).

v2 shares the same SQLite database file as v1. These tables are
v2-specific and do not interfere with v1's tables.
"""
from __future__ import annotations
import sqlite3


SEARCH_LOG_DDL = """
CREATE TABLE IF NOT EXISTS search_log (
    search_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    where_dsl TEXT,
    top_k INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    response_json TEXT NOT NULL
);
"""

EVENT_LOG_DDL = """
CREATE TABLE IF NOT EXISTS event_log (
    event_id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail_json TEXT NOT NULL
);
"""

EVENT_LOG_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_event_log_object
    ON event_log (object_id, at);
"""


def init_v2_schema(conn: sqlite3.Connection) -> None:
    """Create v2 tables if they don't exist. Idempotent."""
    conn.execute(SEARCH_LOG_DDL)
    conn.execute(EVENT_LOG_DDL)
    conn.execute(EVENT_LOG_INDEX_DDL)
    conn.commit()

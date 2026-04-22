"""SQLite schema for v2. All DDL in one place; idempotent init_schema()."""
from __future__ import annotations
import sqlite3


DDL = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id   TEXT PRIMARY KEY,
        source       TEXT NOT NULL,
        created_at   TEXT NOT NULL,
        synced_at    TEXT NOT NULL,
        metadata     TEXT NOT NULL DEFAULT '{}',
        tags         TEXT NOT NULL DEFAULT '[]',
        round_count  INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rounds (
        session_id    TEXT NOT NULL,
        idx           INTEGER NOT NULL,
        round_id      TEXT NOT NULL,
        parent_id     TEXT,
        timestamp     TEXT,
        speaker       TEXT,
        role          TEXT,
        content       TEXT NOT NULL,
        is_sidechain  INTEGER NOT NULL DEFAULT 0,
        cwd           TEXT,
        usage         TEXT,
        PRIMARY KEY (session_id, idx)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rounds_round_id ON rounds(session_id, round_id)",
    """
    CREATE TABLE IF NOT EXISTS cards (
        card_id     TEXT PRIMARY KEY,
        summary     TEXT NOT NULL,
        rounds      TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        expires_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS links (
        link_id      TEXT PRIMARY KEY,
        source_id    TEXT NOT NULL,
        source_type  TEXT NOT NULL,
        target_id    TEXT NOT NULL,
        target_type  TEXT NOT NULL,
        comment      TEXT,
        expires_at   TEXT,
        created_at   TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_id)",
    """
    CREATE TABLE IF NOT EXISTS ingest_log (
        session_id  TEXT NOT NULL,
        sha256      TEXT NOT NULL,
        synced_at   TEXT NOT NULL,
        PRIMARY KEY (session_id, sha256)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_log (
        search_id      TEXT PRIMARY KEY,
        query          TEXT NOT NULL,
        where_dsl      TEXT,
        top_k          INTEGER NOT NULL,
        created_at     TEXT NOT NULL,
        response_json  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_search_log_created ON search_log(created_at)",
    """
    CREATE TABLE IF NOT EXISTS event_log (
        event_id     TEXT PRIMARY KEY,
        object_id    TEXT NOT NULL,
        object_kind  TEXT NOT NULL,
        at           TEXT NOT NULL,
        kind         TEXT NOT NULL,
        detail       TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_event_log_object ON event_log(object_id, at)",
]


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all v2 tables if missing. Idempotent."""
    for stmt in DDL:
        conn.execute(stmt)
    conn.commit()

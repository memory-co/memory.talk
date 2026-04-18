"""Create SQLite tables."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    metadata TEXT,
    tags TEXT,
    round_count INTEGER,
    created_at TEXT,
    synced_at TEXT
);
CREATE TABLE IF NOT EXISTS cards (
    card_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    session_id TEXT,
    expires_at REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    link_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    comment TEXT,
    expires_at REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingest_log (
    source_path TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);
"""

def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.close()

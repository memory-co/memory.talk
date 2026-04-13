"""SQLite implementation of RelationStore."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from memory_talk.models import CardLink, TalkCard
from memory_talk.storage.interfaces import RelationStore


class SQLiteRelationStore(RelationStore):
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_tables(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS cards (
                    card_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    round_start INTEGER NOT NULL,
                    round_end INTEGER NOT NULL,
                    cognition_summary TEXT NOT NULL,
                    compressed_rounds TEXT NOT NULL,
                    token_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS card_links (
                    source_card_id TEXT NOT NULL,
                    target_card_id TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source_card_id, target_card_id, link_type)
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    metadata TEXT,
                    round_count INTEGER,
                    built BOOLEAN DEFAULT FALSE,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS ingest_log (
                    source_path TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def save_card(self, card: TalkCard) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cards
                   (card_id, session_id, round_start, round_end, cognition_summary, compressed_rounds, token_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    card.card_id,
                    card.raw_ref.session_id,
                    card.raw_ref.round_start,
                    card.raw_ref.round_end,
                    card.cognition_summary,
                    card.compressed_rounds,
                    card.token_count,
                    card.created_at.isoformat(),
                ),
            )
            for link in card.links:
                conn.execute(
                    """INSERT OR REPLACE INTO card_links
                       (source_card_id, target_card_id, link_type, weight)
                       VALUES (?, ?, ?, ?)""",
                    (link.source_card_id, link.target_card_id, link.link_type, link.weight),
                )

    def get_card(self, card_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
            if row is None:
                return None
            return dict(row)

    def list_cards(self, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute("SELECT * FROM cards WHERE session_id = ? ORDER BY created_at", (session_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM cards ORDER BY created_at").fetchall()
            return [dict(r) for r in rows]

    def save_link(self, link: CardLink) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO card_links
                   (source_card_id, target_card_id, link_type, weight)
                   VALUES (?, ?, ?, ?)""",
                (link.source_card_id, link.target_card_id, link.link_type, link.weight),
            )

    def get_links(self, card_id: str, link_types: list[str] | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if link_types:
                placeholders = ",".join("?" for _ in link_types)
                rows = conn.execute(
                    f"""SELECT * FROM card_links
                        WHERE (source_card_id = ? OR target_card_id = ?)
                        AND link_type IN ({placeholders})""",
                    (card_id, card_id, *link_types),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM card_links WHERE source_card_id = ? OR target_card_id = ?",
                    (card_id, card_id),
                ).fetchall()
            return [dict(r) for r in rows]

    def save_session(self, session_id: str, source: str, metadata: dict[str, Any], round_count: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions
                   (session_id, source, metadata, round_count, built)
                   VALUES (?, ?, ?, ?, FALSE)""",
                (session_id, source, json.dumps(metadata), round_count),
            )

    def list_sessions(self, unbuilt_only: bool = False) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if unbuilt_only:
                rows = conn.execute("SELECT * FROM sessions WHERE built = FALSE ORDER BY ingested_at").fetchall()
            else:
                rows = conn.execute("SELECT * FROM sessions ORDER BY ingested_at").fetchall()
            return [dict(r) for r in rows]

    def mark_session_built(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sessions SET built = TRUE WHERE session_id = ?", (session_id,))

    def log_ingest(self, source_path: str, session_id: str, file_hash: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO ingest_log (source_path, session_id, file_hash)
                   VALUES (?, ?, ?)""",
                (source_path, session_id, file_hash),
            )

    def is_ingested(self, source_path: str, file_hash: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM ingest_log WHERE source_path = ? AND file_hash = ?",
                (source_path, file_hash),
            ).fetchone()
            return row is not None

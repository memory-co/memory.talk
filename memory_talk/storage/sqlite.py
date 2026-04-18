"""SQLite relational store for sessions, cards, links, and ingest log."""
from __future__ import annotations
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from memory_talk.storage.init_db import init_db


class SQLiteStore:
    def __init__(self, db_path: Path):
        init_db(db_path)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    # ── Sessions ──────────────────────────────────────────────

    def save_session(
        self,
        session_id: str,
        source: str,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        round_count: int = 0,
        created_at: str | None = None,
        synced_at: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO sessions
               (session_id, source, metadata, tags, round_count, created_at, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                source,
                json.dumps(metadata or {}),
                json.dumps(tags or []),
                round_count,
                created_at,
                synced_at,
            ),
        )
        self.conn.commit()

    def list_sessions(self, source: Optional[str] = None) -> list[dict]:
        if source:
            rows = self.conn.execute(
                "SELECT * FROM sessions WHERE source = ? ORDER BY created_at DESC", (source,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
        return [self._parse_session(r) for r in rows]

    def get_session(self, session_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return self._parse_session(row) if row else None

    def add_tags(self, session_id: str, tags: list[str]) -> None:
        row = self.conn.execute(
            "SELECT tags FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return
        existing = json.loads(row["tags"] or "[]")
        merged = list(set(existing + tags))
        self.conn.execute(
            "UPDATE sessions SET tags = ? WHERE session_id = ?",
            (json.dumps(merged), session_id),
        )
        self.conn.commit()

    def remove_tags(self, session_id: str, tags: list[str]) -> None:
        row = self.conn.execute(
            "SELECT tags FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return
        existing = json.loads(row["tags"] or "[]")
        filtered = [t for t in existing if t not in tags]
        self.conn.execute(
            "UPDATE sessions SET tags = ? WHERE session_id = ?",
            (json.dumps(filtered), session_id),
        )
        self.conn.commit()

    def _parse_session(self, row: sqlite3.Row) -> dict:
        return {
            "session_id": row["session_id"],
            "source": row["source"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "tags": json.loads(row["tags"] or "[]"),
            "round_count": row["round_count"],
            "synced_at": row["synced_at"],
        }

    # ── Cards ─────────────────────────────────────────────────

    def save_card(
        self,
        card_id: str,
        summary: str,
        session_id: Optional[str],
        expires_at: float,
        created_at: str,
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO cards
               (card_id, summary, session_id, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (card_id, summary, session_id, expires_at, created_at),
        )
        self.conn.commit()

    def get_card(self, card_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM cards WHERE card_id = ?", (card_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_cards(self, session_id: Optional[str] = None) -> list[dict]:
        now = time.time()
        if session_id:
            rows = self.conn.execute(
                "SELECT * FROM cards WHERE session_id = ? AND expires_at > ?",
                (session_id, now),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM cards WHERE expires_at > ?", (now,)
            ).fetchall()
        return [dict(r) for r in rows]

    def refresh_card_ttl(self, card_id: str, new_expires_at: float) -> None:
        self.conn.execute(
            "UPDATE cards SET expires_at = ? WHERE card_id = ?",
            (new_expires_at, card_id),
        )
        self.conn.commit()

    # ── Links ─────────────────────────────────────────────────

    def save_link(
        self,
        link_id: str,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str,
        comment: Optional[str],
        expires_at: float,
        created_at: str,
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO links
               (link_id, source_id, source_type, target_id, target_type,
                comment, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (link_id, source_id, source_type, target_id, target_type,
             comment, expires_at, created_at),
        )
        self.conn.commit()

    def get_links(
        self,
        object_id: str,
        object_type: Optional[str] = None,
    ) -> list[dict]:
        now = time.time()
        if object_type:
            rows = self.conn.execute(
                """SELECT * FROM links
                   WHERE ((source_id = ? AND source_type = ?)
                       OR (target_id = ? AND target_type = ?))
                     AND expires_at > ?""",
                (object_id, object_type, object_id, object_type, now),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM links
                   WHERE (source_id = ? OR target_id = ?)
                     AND expires_at > ?""",
                (object_id, object_id, now),
            ).fetchall()
        return [dict(r) for r in rows]

    def refresh_link_ttl(self, link_id: str, new_expires_at: float) -> None:
        self.conn.execute(
            "UPDATE links SET expires_at = ? WHERE link_id = ?",
            (new_expires_at, link_id),
        )
        self.conn.commit()

    def delete_link(self, link_id: str) -> None:
        self.conn.execute("DELETE FROM links WHERE link_id = ?", (link_id,))
        self.conn.commit()

    # ── Ingest Log ────────────────────────────────────────────

    def log_ingest(
        self, source_path: str, session_id: str, file_hash: str
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO ingest_log
               (source_path, session_id, file_hash, ingested_at)
               VALUES (?, ?, ?, ?)""",
            (source_path, session_id, file_hash, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def is_ingested(self, source_path: str, file_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT file_hash FROM ingest_log WHERE source_path = ?",
            (source_path,),
        ).fetchone()
        return row is not None and row["file_hash"] == file_hash

    # ── Counts ────────────────────────────────────────────────

    def count_sessions(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()
        return row["cnt"]

    def count_cards(self) -> int:
        now = time.time()
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM cards WHERE expires_at > ?", (now,)
        ).fetchone()
        return row["cnt"]

    def count_links(self) -> int:
        now = time.time()
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM links WHERE expires_at > ?", (now,)
        ).fetchone()
        return row["cnt"]

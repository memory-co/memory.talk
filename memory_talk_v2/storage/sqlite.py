"""SQLiteStore — CRUD on metadata + audit tables.

No full-text search — LanceDB owns all text indexing. This store is the
queryable mirror of file-layer truth: sessions/rounds/cards/links metadata,
ingest_log, search_log, event_log.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Iterable

from memory_talk_v2.storage.schema import init_schema


class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so FastAPI can serve requests from the thread pool.
        # Writes are serialized by sqlite3 itself (one transaction at a time).
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)

    def close(self) -> None:
        self.conn.close()

    # ---------- sessions ----------

    def upsert_session(
        self,
        session_id: str,
        source: str,
        created_at: str,
        synced_at: str,
        metadata: dict,
        tags: list[str],
        round_count: int,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions "
            "(session_id, source, created_at, synced_at, metadata, tags, round_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, source, created_at, synced_at,
             json.dumps(metadata, ensure_ascii=False),
             json.dumps(tags, ensure_ascii=False),
             round_count),
        )
        self.conn.commit()

    def get_session(self, session_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def update_session_tags(self, session_id: str, tags: list[str]) -> None:
        self.conn.execute(
            "UPDATE sessions SET tags = ? WHERE session_id = ?",
            (json.dumps(tags, ensure_ascii=False), session_id),
        )
        self.conn.commit()

    def update_session_round_count(self, session_id: str, count: int, synced_at: str) -> None:
        self.conn.execute(
            "UPDATE sessions SET round_count = ?, synced_at = ? WHERE session_id = ?",
            (count, synced_at, session_id),
        )
        self.conn.commit()

    def count_sessions(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> dict:
        return {
            "session_id": row["session_id"],
            "source": row["source"],
            "created_at": row["created_at"],
            "synced_at": row["synced_at"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "tags": json.loads(row["tags"] or "[]"),
            "round_count": row["round_count"],
        }

    # ---------- rounds ----------

    def upsert_rounds(self, session_id: str, rounds: Iterable[dict]) -> None:
        rows = []
        for r in rounds:
            rows.append((
                session_id, r["idx"], r["round_id"], r.get("parent_id"),
                r.get("timestamp"), r.get("speaker"), r.get("role"),
                json.dumps(r.get("content", []), ensure_ascii=False),
                1 if r.get("is_sidechain") else 0,
                r.get("cwd"),
                json.dumps(r["usage"], ensure_ascii=False) if r.get("usage") is not None else None,
            ))
        self.conn.executemany(
            "INSERT OR REPLACE INTO rounds "
            "(session_id, idx, round_id, parent_id, timestamp, speaker, role, content, is_sidechain, cwd, usage) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def get_round_by_round_id(self, session_id: str, round_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM rounds WHERE session_id = ? AND round_id = ?",
            (session_id, round_id),
        ).fetchone()
        return self._row_to_round(row) if row else None

    def get_round(self, session_id: str, idx: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM rounds WHERE session_id = ? AND idx = ?", (session_id, idx),
        ).fetchone()
        return self._row_to_round(row) if row else None

    def list_rounds(self, session_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM rounds WHERE session_id = ? ORDER BY idx ASC", (session_id,)
        ).fetchall()
        return [self._row_to_round(r) for r in rows]

    def max_round_idx(self, session_id: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(idx), 0) FROM rounds WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row[0]

    @staticmethod
    def _row_to_round(row: sqlite3.Row) -> dict:
        return {
            "session_id": row["session_id"],
            "idx": row["idx"],
            "round_id": row["round_id"],
            "parent_id": row["parent_id"],
            "timestamp": row["timestamp"],
            "speaker": row["speaker"],
            "role": row["role"],
            "content": json.loads(row["content"] or "[]"),
            "is_sidechain": bool(row["is_sidechain"]),
            "cwd": row["cwd"],
            "usage": json.loads(row["usage"]) if row["usage"] else None,
        }

    # ---------- cards ----------

    def insert_card(
        self, card_id: str, summary: str, rounds: list[dict],
        created_at: str, expires_at: str,
    ) -> None:
        self.conn.execute(
            "INSERT INTO cards (card_id, summary, rounds, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (card_id, summary, json.dumps(rounds, ensure_ascii=False), created_at, expires_at),
        )
        self.conn.commit()

    def get_card(self, card_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
        if not row:
            return None
        return {
            "card_id": row["card_id"],
            "summary": row["summary"],
            "rounds": json.loads(row["rounds"] or "[]"),
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }

    def update_card_expires_at(self, card_id: str, expires_at: str) -> None:
        self.conn.execute("UPDATE cards SET expires_at = ? WHERE card_id = ?", (expires_at, card_id))
        self.conn.commit()

    def count_cards(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]

    # ---------- links ----------

    def insert_link(
        self, link_id: str, source_id: str, source_type: str,
        target_id: str, target_type: str, comment: str | None,
        expires_at: str | None, created_at: str,
    ) -> None:
        self.conn.execute(
            "INSERT INTO links (link_id, source_id, source_type, target_id, target_type, comment, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (link_id, source_id, source_type, target_id, target_type, comment, expires_at, created_at),
        )
        self.conn.commit()

    def get_link(self, link_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM links WHERE link_id = ?", (link_id,)).fetchone()
        return self._row_to_link(row) if row else None

    def update_link_expires_at(self, link_id: str, expires_at: str) -> None:
        self.conn.execute("UPDATE links SET expires_at = ? WHERE link_id = ?", (expires_at, link_id))
        self.conn.commit()

    def links_touching(self, object_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM links WHERE source_id = ? OR target_id = ? "
            "ORDER BY created_at ASC",
            (object_id, object_id),
        ).fetchall()
        return [self._row_to_link(r) for r in rows]

    def count_links(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

    @staticmethod
    def _row_to_link(row: sqlite3.Row) -> dict:
        return {
            "link_id": row["link_id"],
            "source_id": row["source_id"],
            "source_type": row["source_type"],
            "target_id": row["target_id"],
            "target_type": row["target_type"],
            "comment": row["comment"],
            "expires_at": row["expires_at"],
            "created_at": row["created_at"],
        }

    # ---------- search_log ----------

    def insert_search_log(
        self, search_id: str, query: str, where_dsl: str | None,
        top_k: int, created_at: str, response_json: str,
    ) -> None:
        self.conn.execute(
            "INSERT INTO search_log (search_id, query, where_dsl, top_k, created_at, response_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (search_id, query, where_dsl, top_k, created_at, response_json),
        )
        self.conn.commit()

    def count_search_log(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM search_log").fetchone()[0]

    # ---------- event_log ----------

    def insert_event(
        self, event_id: str, object_id: str, object_kind: str,
        at: str, kind: str, detail: dict,
    ) -> None:
        self.conn.execute(
            "INSERT INTO event_log (event_id, object_id, object_kind, at, kind, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, object_id, object_kind, at, kind, json.dumps(detail, ensure_ascii=False)),
        )
        self.conn.commit()

    def events_for(self, object_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM event_log WHERE object_id = ? ORDER BY at ASC", (object_id,),
        ).fetchall()
        return [{
            "event_id": r["event_id"],
            "object_id": r["object_id"],
            "object_kind": r["object_kind"],
            "at": r["at"],
            "kind": r["kind"],
            "detail": json.loads(r["detail"] or "{}"),
        } for r in rows]

    def clear_all(self) -> None:
        """Nuke all v2 tables' contents. Used by /v2/rebuild."""
        for t in ("event_log", "search_log", "links", "cards", "rounds", "sessions"):
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.commit()

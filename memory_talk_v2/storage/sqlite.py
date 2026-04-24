"""Async SQLiteStore — CRUD on metadata + audit tables via aiosqlite.

Text search is in LanceDB; this store only mirrors file-layer truth for
queryable metadata and persists the search_log.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable

import aiosqlite

from memory_talk_v2.storage.schema import init_schema


class SQLiteStore:
    def __init__(self, conn: aiosqlite.Connection, db_path: Path):
        self.conn = conn
        self.db_path = db_path

    @classmethod
    async def create(cls, db_path: Path) -> "SQLiteStore":
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await init_schema(conn)
        return cls(conn, db_path)

    async def close(self) -> None:
        await self.conn.close()

    # ---------- sessions ----------

    async def upsert_session(
        self,
        session_id: str,
        source: str,
        created_at: str,
        synced_at: str,
        metadata: dict,
        tags: list[str],
        round_count: int,
    ) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO sessions "
            "(session_id, source, created_at, synced_at, metadata, tags, round_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, source, created_at, synced_at,
             json.dumps(metadata, ensure_ascii=False),
             json.dumps(tags, ensure_ascii=False),
             round_count),
        )
        await self.conn.commit()

    async def get_session(self, session_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_session(row) if row else None

    async def update_session_tags(self, session_id: str, tags: list[str]) -> None:
        await self.conn.execute(
            "UPDATE sessions SET tags = ? WHERE session_id = ?",
            (json.dumps(tags, ensure_ascii=False), session_id),
        )
        await self.conn.commit()

    async def update_session_round_count(self, session_id: str, count: int, synced_at: str) -> None:
        await self.conn.execute(
            "UPDATE sessions SET round_count = ?, synced_at = ? WHERE session_id = ?",
            (count, synced_at, session_id),
        )
        await self.conn.commit()

    async def count_sessions(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM sessions") as cursor:
            row = await cursor.fetchone()
        return row[0]

    @staticmethod
    def _row_to_session(row) -> dict:
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

    async def upsert_rounds(self, session_id: str, rounds: Iterable[dict]) -> None:
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
        await self.conn.executemany(
            "INSERT OR REPLACE INTO rounds "
            "(session_id, idx, round_id, parent_id, timestamp, speaker, role, content, is_sidechain, cwd, usage) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        await self.conn.commit()

    async def get_round_by_round_id(self, session_id: str, round_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM rounds WHERE session_id = ? AND round_id = ?",
            (session_id, round_id),
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_round(row) if row else None

    async def get_round(self, session_id: str, idx: int) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM rounds WHERE session_id = ? AND idx = ?", (session_id, idx),
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_round(row) if row else None

    async def list_rounds(self, session_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM rounds WHERE session_id = ? ORDER BY idx ASC", (session_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_round(r) for r in rows]

    async def max_round_idx(self, session_id: str) -> int:
        async with self.conn.execute(
            "SELECT COALESCE(MAX(idx), 0) FROM rounds WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row[0]

    @staticmethod
    def _row_to_round(row) -> dict:
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

    async def insert_card(
        self, card_id: str, summary: str, rounds: list[dict],
        created_at: str, expires_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO cards (card_id, summary, rounds, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (card_id, summary, json.dumps(rounds, ensure_ascii=False), created_at, expires_at),
        )
        await self.conn.commit()

    async def get_card(self, card_id: str) -> dict | None:
        async with self.conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "card_id": row["card_id"],
            "summary": row["summary"],
            "rounds": json.loads(row["rounds"] or "[]"),
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }

    async def update_card_expires_at(self, card_id: str, expires_at: str) -> None:
        await self.conn.execute(
            "UPDATE cards SET expires_at = ? WHERE card_id = ?", (expires_at, card_id),
        )
        await self.conn.commit()

    async def count_cards(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM cards") as cursor:
            row = await cursor.fetchone()
        return row[0]

    # ---------- links ----------

    async def insert_link(
        self, link_id: str, source_id: str, source_type: str,
        target_id: str, target_type: str, comment: str | None,
        expires_at: str | None, created_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO links (link_id, source_id, source_type, target_id, target_type, comment, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (link_id, source_id, source_type, target_id, target_type, comment, expires_at, created_at),
        )
        await self.conn.commit()

    async def get_link(self, link_id: str) -> dict | None:
        async with self.conn.execute("SELECT * FROM links WHERE link_id = ?", (link_id,)) as cursor:
            row = await cursor.fetchone()
        return self._row_to_link(row) if row else None

    async def update_link_expires_at(self, link_id: str, expires_at: str) -> None:
        await self.conn.execute(
            "UPDATE links SET expires_at = ? WHERE link_id = ?", (expires_at, link_id),
        )
        await self.conn.commit()

    async def links_touching(self, object_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM links WHERE source_id = ? OR target_id = ? "
            "ORDER BY created_at ASC",
            (object_id, object_id),
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_link(r) for r in rows]

    async def count_links(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM links") as cursor:
            row = await cursor.fetchone()
        return row[0]

    @staticmethod
    def _row_to_link(row) -> dict:
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

    async def insert_search_log(
        self, search_id: str, query: str, where_dsl: str | None,
        top_k: int, created_at: str, response_json: str,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO search_log (search_id, query, where_dsl, top_k, created_at, response_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (search_id, query, where_dsl, top_k, created_at, response_json),
        )
        await self.conn.commit()

    async def count_search_log(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM search_log") as cursor:
            row = await cursor.fetchone()
        return row[0]

    async def clear_all(self) -> None:
        """Used by /v2/rebuild."""
        for t in ("search_log", "links", "cards", "rounds", "sessions"):
            await self.conn.execute(f"DELETE FROM {t}")
        await self.conn.commit()

    # ---------- raw helpers used by SearchService DSL whitelist ----------

    async def dsl_cards_whitelist(self, where_sql: str, params: list) -> list[str]:
        async with self.conn.execute(
            f"SELECT card_id FROM cards WHERE {where_sql}", params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def dsl_sessions_whitelist(self, where_sql: str, params: list) -> list[str]:
        async with self.conn.execute(
            f"SELECT session_id FROM sessions WHERE {where_sql}", params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def cards_metadata_filtered(self, whitelist: list[str] | None, top_k: int) -> list[dict]:
        sql = "SELECT card_id, summary, created_at FROM cards"
        params: list = []
        if whitelist is not None:
            placeholders = ",".join("?" * len(whitelist)) or "NULL"
            sql += f" WHERE card_id IN ({placeholders})"
            params.extend(whitelist)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(top_k)
        async with self.conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def sessions_metadata_filtered(self, whitelist: list[str] | None, top_k: int) -> list[dict]:
        sql = "SELECT session_id, source, tags, created_at FROM sessions"
        params: list = []
        if whitelist is not None:
            placeholders = ",".join("?" * len(whitelist)) or "NULL"
            sql += f" WHERE session_id IN ({placeholders})"
            params.extend(whitelist)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(top_k)
        async with self.conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        return [
            {"session_id": r["session_id"], "source": r["source"],
             "tags": json.loads(r["tags"] or "[]"), "created_at": r["created_at"]}
            for r in rows
        ]

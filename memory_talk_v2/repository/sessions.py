"""SessionRepo — async CRUD for sessions + rounds (rounds are session-scoped)."""
from __future__ import annotations
import json
from typing import Iterable

import aiosqlite


class SessionRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    # ---------- sessions table ----------

    async def upsert(
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

    async def get(self, session_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return self._row(row) if row else None

    async def update_tags(self, session_id: str, tags: list[str]) -> None:
        await self.conn.execute(
            "UPDATE sessions SET tags = ? WHERE session_id = ?",
            (json.dumps(tags, ensure_ascii=False), session_id),
        )
        await self.conn.commit()

    async def update_round_count(self, session_id: str, count: int, synced_at: str) -> None:
        await self.conn.execute(
            "UPDATE sessions SET round_count = ?, synced_at = ? WHERE session_id = ?",
            (count, synced_at, session_id),
        )
        await self.conn.commit()

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM sessions") as cursor:
            row = await cursor.fetchone()
        return row[0]

    @staticmethod
    def _row(row) -> dict:
        return {
            "session_id": row["session_id"],
            "source": row["source"],
            "created_at": row["created_at"],
            "synced_at": row["synced_at"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "tags": json.loads(row["tags"] or "[]"),
            "round_count": row["round_count"],
        }

    # ---------- rounds table (session-scoped) ----------

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
        return self._round_row(row) if row else None

    async def get_round(self, session_id: str, idx: int) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM rounds WHERE session_id = ? AND idx = ?", (session_id, idx),
        ) as cursor:
            row = await cursor.fetchone()
        return self._round_row(row) if row else None

    async def list_rounds(self, session_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM rounds WHERE session_id = ? ORDER BY idx ASC", (session_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._round_row(r) for r in rows]

    async def max_round_idx(self, session_id: str) -> int:
        async with self.conn.execute(
            "SELECT COALESCE(MAX(idx), 0) FROM rounds WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row[0]

    @staticmethod
    def _round_row(row) -> dict:
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

    # ---------- search helpers ----------

    async def dsl_whitelist(self, where_sql: str, params: list) -> list[str]:
        """Evaluate a DSL-compiled WHERE fragment against sessions; return matching session_ids."""
        async with self.conn.execute(
            f"SELECT session_id FROM sessions WHERE {where_sql}", params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def metadata_filtered(self, whitelist: list[str] | None, top_k: int) -> list[dict]:
        """Empty-query path: list sessions sorted by created_at DESC, optionally whitelisted."""
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

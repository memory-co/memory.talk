"""SessionStore — session + rounds persistence (file layer + SQLite).

File layout (under storage root):
  sessions/<source>/<bucket>/<session_id>/meta.json
  sessions/<source>/<bucket>/<session_id>/rounds.jsonl
  sessions/<source>/<bucket>/<session_id>/events.jsonl

SQL: ``sessions`` and ``rounds`` tables.
"""
from __future__ import annotations
import json
from typing import Iterable

import aiosqlite

from memory_talk_v2.provider.storage import Storage


class SessionStore:
    PREFIX = "sessions"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage):
        self.conn = conn
        self.storage = storage

    # ---------- file-layer keys ----------

    @staticmethod
    def _bucket(session_id: str) -> str:
        raw = session_id[len("sess_"):] if session_id.startswith("sess_") else session_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _meta_key(self, source: str, session_id: str) -> str:
        return f"{self.PREFIX}/{source}/{self._bucket(session_id)}/{session_id}/meta.json"

    def _rounds_key(self, source: str, session_id: str) -> str:
        return f"{self.PREFIX}/{source}/{self._bucket(session_id)}/{session_id}/rounds.jsonl"

    def _events_key(self, source: str, session_id: str) -> str:
        return f"{self.PREFIX}/{source}/{self._bucket(session_id)}/{session_id}/events.jsonl"

    # ---------- file-layer ops ----------

    async def write_meta(self, source: str, session_id: str, meta: dict) -> None:
        await self.storage.write_text(
            self._meta_key(source, session_id),
            json.dumps(meta, ensure_ascii=False, indent=2),
        )

    async def read_meta(self, source: str, session_id: str) -> dict | None:
        text = await self.storage.read_text(self._meta_key(source, session_id))
        return json.loads(text) if text else None

    async def append_rounds_file(self, source: str, session_id: str, rounds: list[dict]) -> None:
        body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rounds)
        await self.storage.append_text(self._rounds_key(source, session_id), body)

    async def read_rounds_file(self, source: str, session_id: str) -> list[dict]:
        text = await self.storage.read_text(self._rounds_key(source, session_id))
        if not text:
            return []
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    async def append_event(self, source: str, session_id: str, event: dict) -> None:
        await self.storage.append_text(
            self._events_key(source, session_id),
            json.dumps(event, ensure_ascii=False) + "\n",
        )

    async def read_events(self, source: str, session_id: str) -> list[dict]:
        text = await self.storage.read_text(self._events_key(source, session_id))
        if not text:
            return []
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    async def iter_keys(self) -> list[tuple[str, str]]:
        """Returns every (source, session_id) pair found on disk."""
        keys = await self.storage.list_subkeys(self.PREFIX)
        seen: set[tuple[str, str]] = set()
        for k in keys:
            parts = k.split("/")
            # sessions/<source>/<bucket>/<session_id>/<filename>
            if len(parts) >= 5 and parts[0] == self.PREFIX:
                seen.add((parts[1], parts[3]))
        return sorted(seen)

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

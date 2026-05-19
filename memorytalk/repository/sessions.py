"""SessionStore — session metadata (SQL) + rounds (jsonl + small SQL index).

Storage split (v3):

  sessions/<source>/<bucket>/<session_id>/meta.json      ← session metadata mirror
  sessions/<source>/<bucket>/<session_id>/rounds.jsonl   ← full rounds (source of truth)
  sessions/<source>/<bucket>/<session_id>/events.jsonl   ← lifecycle events

  SQLite ``sessions``       ← queryable session metadata (cwd / source / counts)
  SQLite ``rounds_index``   ← {round_id, idx, content_hash} only — ingest-merge key
  SQLite ``ingest_log``     ← sha256 + last_ingest, one per session

  LanceDB ``rounds``        ← per-round {session_id, idx, role, text, vector}
                              for FTS + semantic search (added by IngestService;
                              this module doesn't touch it)
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable

import aiosqlite

from memorytalk.provider.storage import Storage


class SessionStore:
    PREFIX = "sessions"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage):
        self.conn = conn
        self.storage = storage

    # ────────── file-layer keys ──────────

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

    # ────────── file-layer ops ──────────

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
        """Source of truth for rounds. Returns the list in idx order
        (which equals jsonl append order, since we never rewrite the file)."""
        text = await self.storage.read_text(self._rounds_key(source, session_id))
        if not text:
            return []
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    async def append_event(self, source: str, session_id: str, event: dict) -> None:
        await self.storage.append_text(
            self._events_key(source, session_id),
            json.dumps(event, ensure_ascii=False) + "\n",
        )

    # ────────── sessions table ──────────

    async def upsert(
        self,
        session_id: str,
        source: str,
        cwd: str | None,
        created_at: str,
        synced_at: str,
        metadata: dict,
        round_count: int,
    ) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO sessions "
            "(session_id, source, cwd, created_at, synced_at, metadata, round_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, source, cwd, created_at, synced_at,
             json.dumps(metadata, ensure_ascii=False), round_count),
        )
        await self.conn.commit()

    async def get(self, session_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return self._row(row) if row else None

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
            "cwd": row["cwd"],
            "created_at": row["created_at"],
            "synced_at": row["synced_at"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "round_count": row["round_count"],
        }

    # ────────── rounds_index (small SQL index for ingest merge) ──────────

    async def upsert_round_index(
        self, session_id: str, round_id: str, idx: int, content_hash: str,
    ) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO rounds_index "
            "(session_id, round_id, idx, content_hash) VALUES (?, ?, ?, ?)",
            (session_id, round_id, idx, content_hash),
        )
        await self.conn.commit()

    async def upsert_rounds_index(self, rows: Iterable[tuple[str, str, int, str]]) -> None:
        """Batch upsert of (session_id, round_id, idx, content_hash)."""
        await self.conn.executemany(
            "INSERT OR REPLACE INTO rounds_index "
            "(session_id, round_id, idx, content_hash) VALUES (?, ?, ?, ?)",
            list(rows),
        )
        await self.conn.commit()

    async def get_round_index_map(self, session_id: str) -> dict[str, tuple[int, str]]:
        """Return ``{round_id: (idx, content_hash)}`` for the session."""
        async with self.conn.execute(
            "SELECT round_id, idx, content_hash FROM rounds_index "
            "WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return {r["round_id"]: (r["idx"], r["content_hash"]) for r in rows}

    # ────────── ingest_log ──────────

    async def get_ingest(self, session_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT sha256, last_ingest FROM ingest_log WHERE session_id = ?", (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return {"sha256": row[0], "last_ingest": row[1]} if row else None

    async def upsert_ingest(self, session_id: str, sha256: str, last_ingest: str) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO ingest_log (session_id, sha256, last_ingest) "
            "VALUES (?, ?, ?)",
            (session_id, sha256, last_ingest),
        )
        await self.conn.commit()

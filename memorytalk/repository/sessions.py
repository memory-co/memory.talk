"""SessionStore — session metadata (SQL) + rounds (jsonl file mirror).

Storage split (v3):

  sessions/<source>/<bucket>/<session_id>/meta.json      ← session metadata mirror
  sessions/<source>/<bucket>/<session_id>/rounds.jsonl   ← full rounds (source of truth)
  sessions/<source>/<bucket>/<session_id>/events.jsonl   ← lifecycle events

  SQLite ``sessions``       ← queryable metadata + ingest cursor
                              (cwd / source / round_count / last_round_id)

  LanceDB ``rounds``        ← per-round {session_id, idx, role, text, vector}
                              for FTS + semantic search (added by IngestService;
                              this module doesn't touch it)

Sync-side checkpoint (sha256, file offset) lives in a separate sync.db —
see ``repository/sync_checkpoint.py``.
"""
from __future__ import annotations
import json

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
        last_round_id: str | None,
    ) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO sessions "
            "(session_id, source, cwd, created_at, synced_at, metadata, "
            "round_count, last_round_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, source, cwd, created_at, synced_at,
             json.dumps(metadata, ensure_ascii=False),
             round_count, last_round_id),
        )
        await self.conn.commit()

    async def get(self, session_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return self._row(row) if row else None

    async def update_after_append(
        self, session_id: str, count: int, last_round_id: str, synced_at: str,
    ) -> None:
        await self.conn.execute(
            "UPDATE sessions SET round_count = ?, last_round_id = ?, synced_at = ? "
            "WHERE session_id = ?",
            (count, last_round_id, synced_at, session_id),
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
            "last_round_id": row["last_round_id"],
        }

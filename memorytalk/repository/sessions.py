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

    # ─── vector-index tracking ────────────────────────────────────────
    # Backstory: ingest writes rounds to jsonl + SQLite synchronously,
    # then fires-and-forgets the LanceDB vector index. If the embedder
    # fails (e.g. DashScope's 10-batch cap), jsonl/SQLite still hold
    # the data but search silently misses it. These fields let us:
    #   - know which sessions are degraded (a single SQL query, not a
    #     wholesale jsonl walk)
    #   - resume backfill after a crash without re-embedding already-
    #     indexed rounds
    #   - surface the latest failure to the user in `sync status`

    async def bump_indexed_count(
        self, session_id: str, n: int, attempted_at: str,
    ) -> None:
        """Add ``n`` to ``indexed_round_count`` and mark last attempt OK.

        Called once per successfully-flushed embedder batch. Sets
        ``last_index_error = NULL`` so a previously-degraded session
        clears its error state as soon as a batch lands.
        """
        await self.conn.execute(
            "UPDATE sessions SET indexed_round_count = indexed_round_count + ?, "
            "last_index_error = NULL, last_index_attempted_at = ? "
            "WHERE session_id = ?",
            (n, attempted_at, session_id),
        )
        await self.conn.commit()

    async def set_last_index_error(
        self, session_id: str, error: str, attempted_at: str,
    ) -> None:
        """Record a failed embedder batch. Doesn't touch ``indexed_round_count`` —
        previously-indexed rounds are still indexed; this session is just
        stuck partway."""
        await self.conn.execute(
            "UPDATE sessions SET last_index_error = ?, last_index_attempted_at = ? "
            "WHERE session_id = ?",
            (error, attempted_at, session_id),
        )
        await self.conn.commit()

    async def list_degraded(self, limit: int = 50) -> list[dict]:
        """Return sessions whose vector index isn't caught up — i.e.
        ``indexed_round_count < round_count``. Sorted by the gap size
        descending so the biggest backlogs get worked on first."""
        async with self.conn.execute(
            "SELECT * FROM sessions "
            "WHERE indexed_round_count < round_count "
            "ORDER BY (round_count - indexed_round_count) DESC "
            "LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row(r) for r in rows]

    async def get_index_health(self) -> dict:
        """Aggregate snapshot for ``GET /v3/sync/status``."""
        async with self.conn.execute(
            "SELECT "
            "  COUNT(*) AS total_sessions, "
            "  COALESCE(SUM(round_count), 0) AS total_rounds, "
            "  COALESCE(SUM(indexed_round_count), 0) AS indexed_rounds, "
            "  COALESCE(SUM(round_count - indexed_round_count), 0) AS missing_rounds, "
            "  SUM(CASE WHEN indexed_round_count < round_count THEN 1 ELSE 0 END) "
            "    AS degraded_sessions "
            "FROM sessions"
        ) as cursor:
            row = await cursor.fetchone()
        return {
            "total_sessions":    row[0] or 0,
            "total_rounds":      row[1] or 0,
            "indexed_rounds":    row[2] or 0,
            "missing_rounds":    row[3] or 0,
            "degraded_sessions": row[4] or 0,
        }

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
            "indexed_round_count": row["indexed_round_count"] if "indexed_round_count" in row.keys() else 0,
            "last_index_error": row["last_index_error"] if "last_index_error" in row.keys() else None,
            "last_index_attempted_at": row["last_index_attempted_at"] if "last_index_attempted_at" in row.keys() else None,
        }

"""SyncCheckpointStore — per-adapter "what's been pulled from upstream" state.

Lives in its own SQLite file (``~/.memory.talk/sync.db``), distinct from
the main memory DB. Rationale:

- Domain split: the main DB holds the user's memory (sessions, rounds,
  cards, reviews). This store holds "what has sync seen from external
  sources" — a connector-state concern, not a memory concern.
- Wipe semantics: nuking sync state to force a full re-scan is
  ``rm sync.db``, no business-data risk.
- Future remote ingest: if ingest moves out-of-process, sync owns its
  own state without needing to reach into the memory DB.

Schema (one row per upstream session per location):

    source           TEXT          'claude-code' / 'codex' / 'openclaw' / …
    location         TEXT          adapter location URI (filesystem path /
                                   URL). Same source can be ingested from
                                   multiple locations; checkpoint scoped
                                   per (source, location).
    session_id       TEXT          platform-raw id (NOT the minted
                                   sess-<...>-<...>). Local to (source,
                                   location).
    sha256           TEXT          last seen whole-artifact hash (file sha,
                                   HTTP ETag, …). Adapter-defined.
    last_round_id    TEXT|NULL     last round we successfully handed to
                                   ingest. NULL = nothing written yet.
    line_offset      INTEGER       hint: line number in source to seek to
                                   for next read (0-based). For file
                                   adapters this is a perf shortcut;
                                   last_round_id is the source of truth.
    updated_at       TEXT          ISO timestamp of the last upsert.

Keyed by ``(source, location, session_id)``: prevents collisions when
the same upstream id appears at multiple endpoints (e.g. an openclaw
ULID happens to match a local claude-code uuid prefix, or the same
openclaw session id surfaces at both US and EU endpoints).
"""
from __future__ import annotations
from pathlib import Path

import aiosqlite


_DDL = """
CREATE TABLE IF NOT EXISTS sync_session_checkpoint (
    source         TEXT    NOT NULL,
    location       TEXT    NOT NULL DEFAULT '',
    session_id     TEXT    NOT NULL,
    sha256         TEXT    NOT NULL,
    last_round_id  TEXT,
    line_offset    INTEGER NOT NULL DEFAULT 0,
    updated_at     TEXT    NOT NULL,
    PRIMARY KEY (source, location, session_id)
)
"""


class SyncCheckpointStore:
    def __init__(self, conn: aiosqlite.Connection, db_path: Path):
        self.conn = conn
        self.db_path = db_path

    @classmethod
    async def create(cls, db_path: Path) -> "SyncCheckpointStore":
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute(_DDL)
        # Additive migration: older deployments had PK (source, session_id).
        # If the column is missing, add it; old rows get location=''.
        async with conn.execute(
            "PRAGMA table_info(sync_session_checkpoint)"
        ) as cursor:
            cols = {row[1] for row in await cursor.fetchall()}
        if "location" not in cols:
            await conn.execute(
                "ALTER TABLE sync_session_checkpoint "
                "ADD COLUMN location TEXT NOT NULL DEFAULT ''"
            )
        await conn.commit()
        return cls(conn, db_path)

    async def close(self) -> None:
        await self.conn.close()

    async def get(self, source: str, location: str, session_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT sha256, last_round_id, line_offset, updated_at "
            "FROM sync_session_checkpoint "
            "WHERE source = ? AND location = ? AND session_id = ?",
            (source, location, session_id),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "sha256": row["sha256"],
            "last_round_id": row["last_round_id"],
            "line_offset": row["line_offset"],
            "updated_at": row["updated_at"],
        }

    async def upsert(
        self,
        source: str,
        location: str,
        session_id: str,
        sha256: str,
        last_round_id: str | None,
        line_offset: int,
        updated_at: str,
    ) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO sync_session_checkpoint "
            "(source, location, session_id, sha256, last_round_id, line_offset, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (source, location, session_id, sha256, last_round_id, line_offset, updated_at),
        )
        await self.conn.commit()

    async def count(self) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM sync_session_checkpoint"
        ) as cursor:
            row = await cursor.fetchone()
        return row[0]

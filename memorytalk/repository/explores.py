"""ExploreStore — the thin SQLite index for explores.

The rich per-exploration detail is file-canonical inside the workspace
directory (see explore.md); this store keeps only what drives queries:
the divider, the workspace path, provenance.
"""
from __future__ import annotations

import aiosqlite


class ExploreStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
        self,
        explore_id: str,
        *,
        dir_path: str,
        divider_at: str,
        entrypoint_session_id: str | None,
        created_at: str,
        note: str | None = None,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO explores "
            "(explore_id, dir_path, divider_at, entrypoint_session_id, "
            " created_at, note) VALUES (?, ?, ?, ?, ?, ?)",
            (explore_id, dir_path, divider_at, entrypoint_session_id,
             created_at, note),
        )
        await self.conn.commit()

    async def get(self, explore_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT explore_id, dir_path, divider_at, entrypoint_session_id, "
            "created_at, note FROM explores WHERE explore_id = ?",
            (explore_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "explore_id": row[0],
            "dir_path": row[1],
            "divider_at": row[2],
            "entrypoint_session_id": row[3],
            "created_at": row[4],
            "note": row[5],
        }

    async def list(self, limit: int = 50) -> list[dict]:
        async with self.conn.execute(
            "SELECT explore_id, dir_path, divider_at, entrypoint_session_id, "
            "created_at, note FROM explores ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "explore_id": r[0], "dir_path": r[1], "divider_at": r[2],
                "entrypoint_session_id": r[3], "created_at": r[4], "note": r[5],
            }
            for r in rows
        ]

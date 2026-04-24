"""LinkRepo — async CRUD for links table."""
from __future__ import annotations

import aiosqlite


class LinkRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(
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

    async def get(self, link_id: str) -> dict | None:
        async with self.conn.execute("SELECT * FROM links WHERE link_id = ?", (link_id,)) as cursor:
            row = await cursor.fetchone()
        return self._row(row) if row else None

    async def update_expires_at(self, link_id: str, expires_at: str) -> None:
        await self.conn.execute(
            "UPDATE links SET expires_at = ? WHERE link_id = ?", (expires_at, link_id),
        )
        await self.conn.commit()

    async def touching(self, object_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM links WHERE source_id = ? OR target_id = ? "
            "ORDER BY created_at ASC",
            (object_id, object_id),
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row(r) for r in rows]

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM links") as cursor:
            row = await cursor.fetchone()
        return row[0]

    @staticmethod
    def _row(row) -> dict:
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

"""SessionMarkStore -- mark metadata index (session_marks).

A mark is a session's subordinate annotation, addressed ``<session_id>#m<n>``
(``m`` + a session-scoped seq). The seq is minted on insert from the current
max mark for the session (+1). Body lives in marks/m<n>.yaml (canonical);
this table holds the metadata (seq / last_index optimistic-lock baseline /
time) for addressing, reverse lookup and the optimistic lock. No own id;
composite PK (session_id, mark). No FOREIGN KEY.
"""
from __future__ import annotations

import aiosqlite

from memorytalk.util.ids import mark_seq


class SessionMarkStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def next_seq(self, session_id: str) -> str:
        """The next session-scoped mark seq ('m<n>') for a session."""
        async with self.conn.execute(
            "SELECT COUNT(*) AS n FROM session_marks WHERE session_id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        return mark_seq((row["n"] if row else 0) + 1)

    async def insert(
        self, session_id: str, last_index: int, created_at: str,
    ) -> str:
        """Mint the next ``m<n>`` for the session, insert the row. Returns it."""
        mark = await self.next_seq(session_id)
        await self.conn.execute(
            "INSERT INTO session_marks (session_id, mark, last_index, created_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, mark, last_index, created_at),
        )
        await self.conn.commit()
        return mark

    async def get(self, session_id: str, mark: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM session_marks WHERE session_id = ? AND mark = ?",
            (session_id, mark),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def delete_for_session(self, session_id: str) -> int:
        """Delete every mark row for a session (cleanup). Returns the row
        count removed. Leaves the canonical YAML to the file store."""
        cur = await self.conn.execute(
            "DELETE FROM session_marks WHERE session_id = ?", (session_id,),
        )
        await self.conn.commit()
        return cur.rowcount

    async def list_for_session(self, session_id: str) -> list[dict]:
        # Secondary ``rowid`` (insertion) order breaks ties: a whole batch of
        # marks shares one second-resolution ``created_at``, so created_at
        # alone leaves intra-batch order undefined; rowid restores m1,m2,m3…
        async with self.conn.execute(
            "SELECT * FROM session_marks WHERE session_id = ? "
            "ORDER BY created_at ASC, rowid ASC",
            (session_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

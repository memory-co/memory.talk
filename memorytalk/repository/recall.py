"""RecallStore — recall + recall_hit persistence (SQLite-only).

Two tables:
- ``recall`` (one row per session) — holds the atomic round counter that
  serves as the primary-key component for ``recall_hit``. Also doubles as
  the per-session aggregate the ``review`` command queries directly.
- ``recall_hit`` (one row per (session, card, round)) — every card that
  was actually injected; rows are NOT written for cards filtered by the
  sliding-window dedup (those decisions are reproducible from the same
  history without needing to be persisted).

This data is **SQLite-only** by design. ``rebuild`` clears it; that's
acceptable for an ephemeral, session-scoped state.
"""
from __future__ import annotations
from typing import Iterable

import aiosqlite


class RecallStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    # ---------- recall table ----------

    async def bump_round(self, session_id: str, *, query: str, now_iso: str) -> int:
        """Atomically create or increment the session's round_count and return
        the new value. UPSERT + RETURNING in one statement, so concurrent
        calls always get distinct round numbers.
        """
        async with self.conn.execute(
            """
            INSERT INTO recall (session_id, round_count, first_at, last_at, last_query)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                round_count = round_count + 1,
                last_at = excluded.last_at,
                last_query = excluded.last_query
            RETURNING round_count
            """,
            (session_id, now_iso, now_iso, query),
        ) as cursor:
            row = await cursor.fetchone()
        await self.conn.commit()
        return int(row[0])

    async def get(self, session_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM recall WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return self._row(row)

    async def list_sessions(self, limit: int = 100) -> list[dict]:
        """Powers the ``review`` command: every session that has any recall
        history, plus aggregate stats. Joins recall_hit for ``cards_injected``."""
        async with self.conn.execute(
            """
            SELECT
                r.session_id, r.round_count, r.first_at, r.last_at, r.last_query,
                COUNT(DISTINCT h.card_id) AS cards_injected
            FROM recall r
            LEFT JOIN recall_hit h USING(session_id)
            GROUP BY r.session_id
            ORDER BY r.last_at DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        out = []
        for r in rows:
            d = self._row(r)
            d["cards_injected"] = int(r["cards_injected"] or 0)
            out.append(d)
        return out

    @staticmethod
    def _row(row) -> dict:
        return {
            "session_id": row["session_id"],
            "round_count": row["round_count"],
            "first_at": row["first_at"],
            "last_at": row["last_at"],
            "last_query": row["last_query"],
        }

    # ---------- recall_hit table ----------

    async def record_hits(
        self, session_id: str, *,
        round_count: int, query: str, now_iso: str,
        hits: Iterable[tuple[str, int]],   # iterable of (card_id, rank)
    ) -> None:
        rows = [
            (session_id, card_id, round_count, rank, query, now_iso)
            for card_id, rank in hits
        ]
        if not rows:
            return
        await self.conn.executemany(
            """
            INSERT INTO recall_hit
                (session_id, card_id, round_count, rank, query, recalled_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        await self.conn.commit()

    async def seen_in_window(
        self, session_id: str, card_ids: list[str],
        *, current_round: int, window: int,
    ) -> set[str]:
        """Return the subset of ``card_ids`` that were already injected for
        this session within the last ``window`` rounds (i.e. round_count >
        current_round - window). The current round itself isn't yet in the
        table — the caller invokes this BEFORE record_hits."""
        if not card_ids or window <= 0:
            return set()
        placeholders = ",".join("?" * len(card_ids))
        async with self.conn.execute(
            f"""
            SELECT DISTINCT card_id FROM recall_hit
            WHERE session_id = ?
              AND card_id IN ({placeholders})
              AND round_count > ?
            """,
            (session_id, *card_ids, current_round - window),
        ) as cursor:
            rows = await cursor.fetchall()
        return {r[0] for r in rows}

    async def list_hits(self, session_id: str, *, round_count: int | None = None) -> list[dict]:
        """For audit / view use — every hit for this session, optionally
        filtered to a single round."""
        if round_count is not None:
            sql = (
                "SELECT * FROM recall_hit "
                "WHERE session_id = ? AND round_count = ? "
                "ORDER BY rank ASC"
            )
            params = (session_id, round_count)
        else:
            sql = (
                "SELECT * FROM recall_hit "
                "WHERE session_id = ? "
                "ORDER BY round_count ASC, rank ASC"
            )
            params = (session_id,)
        async with self.conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "session_id": r["session_id"],
                "card_id": r["card_id"],
                "round_count": r["round_count"],
                "rank": r["rank"],
                "query": r["query"],
                "recalled_at": r["recalled_at"],
            }
            for r in rows
        ]

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM recall_hit") as cursor:
            row = await cursor.fetchone()
        return row[0]

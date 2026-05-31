"""RecallStore — derived SQLite index over ``recall.jsonl`` files.

The canonical store is the per-session ``recall.jsonl`` file under
``sessions/<source>/<sid[0:2]>/<sid>/`` (see
``docs/structure/v3/recall.md``). This module is a query index only;
all SQLite rows are reproducible from the corresponding file lines.

Schema:

    recall_event(
        event_id     TEXT PRIMARY KEY,
        session_id   TEXT NOT NULL,
        prompt       TEXT NOT NULL,
        ts           TEXT NOT NULL,
        returned_ids TEXT NOT NULL,   -- JSON array of card_id strings
        skipped_ids  TEXT NOT NULL    -- JSON array of card_id strings
    )

All dedup / list / read / popularity queries derive from this table
via ``json_each`` against the JSON array columns.
"""
from __future__ import annotations

import json

import aiosqlite


class RecallStore:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    # ─────────── dedup (hook write-path) ───────────

    async def already_recalled(
        self, session_id: str, candidate_card_ids: list[str],
    ) -> set[str]:
        """Subset of ``candidate_card_ids`` already returned in any
        prior ``recall_event`` for this session."""
        if not candidate_card_ids:
            return set()
        # json_each unrolls returned_ids into one row per card. We
        # filter on session_id (covered by index) first, then on
        # j.value being one of the candidates.
        placeholders = ",".join("?" * len(candidate_card_ids))
        async with self.conn.execute(
            f"SELECT DISTINCT j.value FROM recall_event, "
            f"json_each(recall_event.returned_ids) AS j "
            f"WHERE recall_event.session_id = ? "
            f"AND j.value IN ({placeholders})",
            [session_id, *candidate_card_ids],
        ) as cursor:
            rows = await cursor.fetchall()
        return {r[0] for r in rows}

    # ─────────── insert (hook write-path, file-first contract) ───────────

    async def insert_event(
        self,
        *,
        event_id: str,
        session_id: str,
        prompt: str,
        ts: str,
        returned_card_ids: list[str],
        skipped_card_ids: list[str],
    ) -> None:
        """Insert one row into ``recall_event``. Caller MUST have already
        written the canonical ``recall.jsonl`` line — this is the
        derived index, file is canonical.

        Failures are propagated to the caller, which is expected to log
        and continue (per the hook contract: SQLite drift is recoverable
        via future rebuild, file already has the truth)."""
        await self.conn.execute(
            "INSERT INTO recall_event "
            "(event_id, session_id, prompt, ts, returned_ids, skipped_ids) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event_id, session_id, prompt, ts,
                json.dumps(returned_card_ids, ensure_ascii=False),
                json.dumps(skipped_card_ids, ensure_ascii=False),
            ),
        )
        await self.conn.commit()

    # ─────────── list-sessions view (``recall list``) ───────────

    async def list_sessions(self, *, limit: int = 20) -> list[dict]:
        """Per-session aggregate: how many recall events, last-recall
        timestamp, distinct returned cards. Sorted by most-recent
        recall first."""
        # SUM(json_array_length(returned_ids)) gives total returned card
        # slots (counting duplicates if any — but our dedup contract
        # forbids dupes within a session). For "unique cards" we want
        # DISTINCT across the json_each unfold.
        async with self.conn.execute(
            "SELECT session_id, "
            "       COUNT(*) AS recalls, "
            "       MAX(ts) AS last_recall, "
            "       ( "
            "           SELECT COUNT(DISTINCT j.value) "
            "             FROM recall_event re2, "
            "                  json_each(re2.returned_ids) AS j "
            "            WHERE re2.session_id = recall_event.session_id "
            "       ) AS unique_cards "
            "  FROM recall_event "
            " GROUP BY session_id "
            " ORDER BY last_recall DESC "
            " LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "session_id": r[0],
                "recalls": r[1],
                "last_recall": r[2],
                "unique_cards": r[3],
            }
            for r in rows
        ]

    # ─────────── read-session view (``recall read <sid>``) ───────────

    async def get_session_events(
        self,
        session_id: str,
        *,
        limit: int = 50,
        reverse: bool = False,
    ) -> list[dict]:
        """Timeline of recall events for one session. Default order:
        chronological (oldest → newest); ``reverse=True`` flips it."""
        order = "DESC" if reverse else "ASC"
        async with self.conn.execute(
            f"SELECT event_id, session_id, prompt, ts, "
            f"       returned_ids, skipped_ids "
            f"  FROM recall_event "
            f" WHERE session_id = ? "
            f" ORDER BY ts {order}, event_id {order} "
            f" LIMIT ?",
            (session_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "event_id": r[0],
                "session_id": r[1],
                "prompt": r[2],
                "ts": r[3],
                "returned_ids": json.loads(r[4]),
                "skipped_ids": json.loads(r[5]),
            }
            for r in rows
        ]

    # ─────────── derived popularity (search/read display) ───────────

    async def recall_counts(self, card_ids: list[str]) -> dict[str, int]:
        """How many times each card has been *returned* by recall hook
        across all sessions. Returns 0 for any card_id with no recalls.

        This replaces the old ``card_stats.recall_count`` column —
        derived on read, single source of truth, no drift possible."""
        if not card_ids:
            return {}
        placeholders = ",".join("?" * len(card_ids))
        async with self.conn.execute(
            f"SELECT j.value, COUNT(*) "
            f"  FROM recall_event, json_each(recall_event.returned_ids) AS j "
            f" WHERE j.value IN ({placeholders}) "
            f" GROUP BY j.value",
            card_ids,
        ) as cursor:
            rows = await cursor.fetchall()
        counts = {r[0]: r[1] for r in rows}
        # Cards with zero recalls don't appear in the query — fill them
        # in explicitly so callers can do dict lookups without KeyError.
        for cid in card_ids:
            counts.setdefault(cid, 0)
        return counts

    # ─────────── ops ───────────

    async def count(self) -> int:
        """Total ``recall_event`` row count (ops / stats / tests)."""
        async with self.conn.execute(
            "SELECT COUNT(*) FROM recall_event",
        ) as cursor:
            row = await cursor.fetchone()
        return row[0]

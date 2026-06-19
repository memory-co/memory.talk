"""InsightStore — read-only persistence for the old v3 card ("insight").

Insights are the renamed v3 card subsystem, kept READ-ONLY in v4: data is
preserved (search + view), but nothing new is written and nothing is
mutated. Id VALUES carry the ``insight_`` prefix; the SQLite COLUMN names
stay ``card_id`` / ``source_card_id`` (only the values were rewritten by
the v3 migration), and the dict surface this store returns uses
``insight_id``.

File layout (read-only)::

    insights/<bucket>/<insight_id>/card.json      (immutable payload mirror)
    insights/<bucket>/<insight_id>/events.jsonl   (historical events)
"""
from __future__ import annotations
import json
from typing import AsyncIterator

import aiosqlite

from memorytalk.provider.storage import Storage


class InsightStore:
    PREFIX = "insights"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage):
        self.conn = conn
        self.storage = storage

    # ────────── file-layer keys ──────────

    @staticmethod
    def _bucket(insight_id: str) -> str:
        raw = (
            insight_id[len("insight_"):]
            if insight_id.startswith("insight_")
            else insight_id
        )
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _doc_key(self, insight_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(insight_id)}/{insight_id}/card.json"

    # ────────── file-layer reads ──────────

    async def read_doc(self, insight_id: str) -> dict | None:
        text = await self.storage.read_text(self._doc_key(insight_id))
        return json.loads(text) if text else None

    async def iter_docs(self) -> AsyncIterator[dict]:
        keys = await self.storage.list_subkeys(self.PREFIX)
        for k in keys:
            if k.endswith("/card.json"):
                text = await self.storage.read_text(k)
                if text:
                    yield json.loads(text)

    # ────────── insights table ──────────

    async def get(self, insight_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM insights WHERE card_id = ?", (insight_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        keys = row.keys()
        return {
            "insight_id": row["card_id"],
            "insight": row["insight"],
            "rounds": json.loads(row["rounds"] or "[]"),
            "tags": json.loads(row["tags"] or "{}") if "tags" in keys else {},
            "created_at": row["created_at"],
        }

    async def exists(self, insight_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM insights WHERE card_id = ?", (insight_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM insights") as cursor:
            row = await cursor.fetchone()
        return row[0]

    # ────────── insight_stats (read-only) ──────────

    async def get_stats(self, insight_id: str) -> dict:
        """Return the stats row (all zeros if missing).

        Does NOT include ``recall_count`` — that's derived. Display-layer
        callers merge in ``RecallStore.recall_counts([insight_id])``."""
        async with self.conn.execute(
            "SELECT review_up, review_down, review_neutral, review_count, "
            "read_count FROM insight_stats WHERE card_id = ?",
            (insight_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return {
                "review_up": 0, "review_down": 0, "review_neutral": 0,
                "review_count": 0, "read_count": 0,
            }
        return {
            "review_up": row["review_up"],
            "review_down": row["review_down"],
            "review_neutral": row["review_neutral"],
            "review_count": row["review_count"],
            "read_count": row["read_count"],
        }

    # ────────── insight_source_cards (read-only) ──────────

    async def list_source_cards(self, insight_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT source_card_id, relation FROM insight_source_cards "
            "WHERE card_id = ? ORDER BY seq ASC",
            (insight_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {"insight_id": r["source_card_id"], "relation": r["relation"]}
            for r in rows
        ]

    async def count_inbound_refs(self, insight_id: str) -> int:
        """How many *other* insights reference this one via source_cards."""
        async with self.conn.execute(
            "SELECT COUNT(*) FROM insight_source_cards WHERE source_card_id = ?",
            (insight_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row[0]

    # ────────── list + tags (read-only) ──────────

    async def list_cards(
        self,
        *,
        tag_filters=None,  # list[TagPredicate] | None
        since: str | None = None,
        until: str | None = None,
        limit: int = 20,
    ) -> tuple[int, list[dict]]:
        """Filtered insight list for ``GET /v4/insights``.

        Returns ``(total, rows)`` where each row carries the insight's
        immutable fields + tags + stats (joined). Structural filters only
        (tag / time); stats filters go through ``search "" -w 'DSL'``.
        """
        from memorytalk.util.tag_filter import to_sql as _tag_sql

        clauses: list[str] = []
        params: list = []

        if tag_filters:
            t_clauses, t_params = _tag_sql(tag_filters, column="tags")
            clauses.extend(t_clauses)
            params.extend(t_params)

        if since:
            clauses.append("created_at >= ?")
            params.append(since)

        if until:
            clauses.append("created_at <= ?")
            params.append(until)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        async with self.conn.execute(
            f"SELECT COUNT(*) FROM insights {where}", params,
        ) as cur:
            total = (await cur.fetchone())[0]

        async with self.conn.execute(
            f"SELECT c.card_id, c.insight, c.tags, c.created_at, "
            f"       COALESCE(s.review_up, 0)      AS review_up, "
            f"       COALESCE(s.review_down, 0)    AS review_down, "
            f"       COALESCE(s.review_neutral, 0) AS review_neutral, "
            f"       COALESCE(s.review_count, 0)   AS review_count, "
            f"       COALESCE(s.read_count, 0)     AS read_count "
            f"FROM insights c LEFT JOIN insight_stats s ON c.card_id = s.card_id "
            f"{where} ORDER BY c.created_at DESC LIMIT ?",
            params + [limit],
        ) as cur:
            rows = await cur.fetchall()
        out: list[dict] = []
        for r in rows:
            out.append({
                "insight_id": r["card_id"],
                "insight": r["insight"],
                "tags": json.loads(r["tags"] or "{}"),
                "created_at": r["created_at"],
                "stats": {
                    "review_up":      r["review_up"],
                    "review_down":    r["review_down"],
                    "review_neutral": r["review_neutral"],
                    "review_count":   r["review_count"],
                    "read_count":     r["read_count"],
                },
            })
        return total, out

    async def get_tags(self, insight_id: str) -> dict | None:
        """Return tags dict or ``None`` if the insight row doesn't exist."""
        async with self.conn.execute(
            "SELECT tags FROM insights WHERE card_id = ?", (insight_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return json.loads(row["tags"] or "{}")

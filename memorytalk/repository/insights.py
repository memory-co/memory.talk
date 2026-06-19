"""InsightStore — insight persistence (file layer + SQLite).

File layout::

    insights/<bucket>/<card_id>/card.json        (immutable payload mirror)
    insights/<bucket>/<card_id>/events.jsonl     (created / read / recalled)

The ``insight_stats`` and ``insight_source_cards`` tables hold runtime state +
edges; ``insights`` itself holds immutable payload (insight + rounds JSON).
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
    def _bucket(card_id: str) -> str:
        raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _card_dir_key(self, card_id: str) -> str:
        """Per-card directory prefix; used by ``delete_files`` to rmtree
        the whole card footprint (card.json + events.jsonl + tags.json)
        in one shot."""
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}"

    def _doc_key(self, card_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/card.json"

    def _events_key(self, card_id: str) -> str:
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/events.jsonl"

    def _tags_key(self, card_id: str) -> str:
        # tags live in their own sidecar so card.json stays the
        # immutable-payload mirror — `card create` writes card.json once,
        # `card tag` PATCH writes tags.json without touching card.json.
        return f"{self.PREFIX}/{self._bucket(card_id)}/{card_id}/tags.json"

    # ────────── file-layer ops ──────────

    async def write_doc(self, card: dict) -> None:
        await self.storage.write_text(
            self._doc_key(card["card_id"]),
            json.dumps(card, ensure_ascii=False, indent=2),
        )

    async def read_doc(self, card_id: str) -> dict | None:
        text = await self.storage.read_text(self._doc_key(card_id))
        return json.loads(text) if text else None

    async def append_event(self, card_id: str, event: dict) -> None:
        await self.storage.append_text(
            self._events_key(card_id),
            json.dumps(event, ensure_ascii=False) + "\n",
        )

    async def read_tags_file(self, card_id: str) -> dict:
        """Read tags.json sidecar (or empty dict if missing)."""
        text = await self.storage.read_text(self._tags_key(card_id))
        return json.loads(text) if text else {}

    async def write_tags_file(self, card_id: str, tags: dict) -> None:
        await self.storage.write_text(
            self._tags_key(card_id),
            json.dumps(tags, ensure_ascii=False, indent=2),
        )

    async def iter_docs(self) -> AsyncIterator[dict]:
        keys = await self.storage.list_subkeys(self.PREFIX)
        for k in keys:
            if k.endswith("/card.json"):
                text = await self.storage.read_text(k)
                if text:
                    yield json.loads(text)

    # ────────── cards table ──────────

    async def insert(
        self, card_id: str, insight: str, rounds: list[dict],
        created_at: str, tags: dict | None = None,
        explore_id: str | None = None,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO insights "
            "(card_id, insight, rounds, tags, created_at, explore_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (card_id, insight,
             json.dumps(rounds, ensure_ascii=False),
             json.dumps(tags or {}, ensure_ascii=False),
             created_at, explore_id),
        )
        await self.conn.commit()

    async def get(self, card_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM insights WHERE card_id = ?", (card_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        keys = row.keys()
        return {
            "card_id": row["card_id"],
            "insight": row["insight"],
            "rounds": json.loads(row["rounds"] or "[]"),
            "tags": json.loads(row["tags"] or "{}") if "tags" in keys else {},
            "created_at": row["created_at"],
        }

    async def exists(self, card_id: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM insights WHERE card_id = ?", (card_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM insights") as cursor:
            row = await cursor.fetchone()
        return row[0]

    # ────────── insight_stats ──────────

    async def init_stats(self, card_id: str, now: str) -> None:
        """Insert a stats row for a freshly created card (all zeros).

        ``recall_count`` is intentionally not a column anymore (0.9.0).
        Recall popularity is derived from ``recall_event`` at read time
        via ``RecallStore.recall_counts``."""
        await self.conn.execute(
            "INSERT INTO insight_stats "
            "(card_id, review_up, review_down, review_neutral, review_count, "
            " read_count, updated_at) "
            "VALUES (?, 0, 0, 0, 0, 0, ?)",
            (card_id, now),
        )
        await self.conn.commit()

    async def get_stats(self, card_id: str) -> dict:
        """Return the stats row (all zeros if missing — happens for tests that
        create card rows directly without the service).

        Does NOT include ``recall_count`` — that's derived. Display-layer
        callers should merge in ``RecallStore.recall_counts([card_id])``
        when they need it."""
        async with self.conn.execute(
            "SELECT review_up, review_down, review_neutral, review_count, "
            "read_count FROM insight_stats WHERE card_id = ?",
            (card_id,),
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

    async def bump_read(self, card_id: str, now: str, delta: int = 1) -> None:
        await self.conn.execute(
            "UPDATE insight_stats SET read_count = read_count + ?, updated_at = ? "
            "WHERE card_id = ?",
            (delta, now, card_id),
        )
        await self.conn.commit()

    # ────────── insight_source_cards ──────────

    async def insert_source_cards(self, card_id: str, items: list[dict]) -> None:
        """Insert source_cards rows in declared order."""
        if not items:
            return
        rows = [
            (card_id, i, item["card_id"], item["relation"])
            for i, item in enumerate(items)
        ]
        await self.conn.executemany(
            "INSERT INTO insight_source_cards "
            "(card_id, seq, source_card_id, relation) VALUES (?, ?, ?, ?)",
            rows,
        )
        await self.conn.commit()

    async def list_source_cards(self, card_id: str) -> list[dict]:
        async with self.conn.execute(
            "SELECT source_card_id, relation FROM insight_source_cards "
            "WHERE card_id = ? ORDER BY seq ASC",
            (card_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [{"card_id": r["source_card_id"], "relation": r["relation"]} for r in rows]

    async def count_inbound_refs(self, card_id: str) -> int:
        """How many *other* cards reference this card via source_cards
        (i.e. would be left with a dangling reference if we delete it).
        Covered by ``idx_csc_source``."""
        async with self.conn.execute(
            "SELECT COUNT(*) FROM insight_source_cards WHERE source_card_id = ?",
            (card_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row[0]

    # ────────── delete (0.9.x) ──────────

    async def delete(self, card_id: str) -> None:
        """Atomic SQLite tx removing the card row + everything 1:1 with it
        (``insight_stats``, outbound ``insight_source_cards``). Caller is
        responsible for reviews (separate store) + vector + files.

        ``insight_source_cards`` rows where ``source_card_id = card_id``
        (inbound refs) are intentionally LEFT IN PLACE — see
        ``count_inbound_refs``. The other card's "references this one"
        link becomes dangling, but cascading deletes upstream would
        be a destructive surprise."""
        # Single transaction so a mid-flight failure leaves no
        # half-state (no orphan insight_stats / source_cards rows).
        await self.conn.execute(
            "DELETE FROM insight_source_cards WHERE card_id = ?", (card_id,),
        )
        await self.conn.execute(
            "DELETE FROM insight_stats WHERE card_id = ?", (card_id,),
        )
        await self.conn.execute(
            "DELETE FROM insights WHERE card_id = ?", (card_id,),
        )
        await self.conn.commit()

    async def delete_files(self, card_id: str) -> None:
        """Recursively remove the card's per-card directory (card.json,
        events.jsonl, tags.json). Best-effort — missing directory is a
        no-op."""
        await self.storage.delete_prefix(self._card_dir_key(card_id))

    # ─── 0.8.x: list + user-side tags ──────────────────────────────

    async def list_cards(
        self,
        *,
        tag_filters=None,  # list[TagPredicate] | None
        since: str | None = None,
        until: str | None = None,
        limit: int = 20,
    ) -> tuple[int, list[dict]]:
        """Filtered card list for ``GET /v3/cards``.

        Returns ``(total, rows)`` where each row carries the card's
        immutable fields + tags + stats (joined). ``rows`` is the page
        (``limit`` longest, ``created_at`` desc); ``total`` is the
        unbounded match count so the CLI can show "23 of 1247".

        Filter set is intentionally **structural only** (tag / time) —
        ``review_up >= N``-style stats filters go through
        ``search "" -w 'DSL'`` instead. Keeps the two commands' jobs
        cleanly separated.
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

        # LEFT JOIN insight_stats so cards without an explicit stats row
        # (legacy DBs, tests that hit ``insert`` directly) still render
        # with all-zeros instead of being filtered out by an inner join.
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
                "card_id": r["card_id"],
                "insight": r["insight"],
                "tags": json.loads(r["tags"] or "{}"),
                "created_at": r["created_at"],
                "stats": {
                    "review_up":      r["review_up"],
                    "review_down":    r["review_down"],
                    "review_neutral": r["review_neutral"],
                    "review_count":   r["review_count"],
                    "read_count":     r["read_count"],
                    # recall_count merged in by service layer via
                    # RecallStore.recall_counts() — derived, not stored.
                },
            })
        return total, out

    async def get_tags(self, card_id: str) -> dict | None:
        """Return tags dict or ``None`` if the card row doesn't exist."""
        async with self.conn.execute(
            "SELECT tags FROM insights WHERE card_id = ?", (card_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return json.loads(row["tags"] or "{}")

    async def replace_tags(self, card_id: str, tags: dict) -> bool:
        """Wholesale rewrite of the tags column + tags.json sidecar.

        Tags assumed already validated (call ``util.tags.apply_patch``
        first). Returns False when the card row is missing so API can
        return 404 without a separate existence check.

        File mirror: writes ``tags.json`` next to ``card.json``. We
        write a separate file (not into card.json) because card.json is
        the immutable payload mirror — touching it breaks the
        append-only invariant.
        """
        if not await self.exists(card_id):
            return False
        await self.conn.execute(
            "UPDATE insights SET tags = ? WHERE card_id = ?",
            (json.dumps(tags, ensure_ascii=False), card_id),
        )
        await self.conn.commit()
        await self.write_tags_file(card_id, tags)
        return True

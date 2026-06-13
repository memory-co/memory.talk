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

    def _recall_key(self, source: str, session_id: str) -> str:
        """0.9.0: per-session canonical recall log (one line per hook call).
        Sits alongside meta/rounds/events under the same session dir so
        a session's whole footprint is in one place on disk."""
        return f"{self.PREFIX}/{source}/{self._bucket(session_id)}/{session_id}/recall.jsonl"

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

    async def append_recall_event(
        self, source: str, session_id: str, event: dict,
    ) -> None:
        """0.9.0: append one recall event line to the canonical
        ``recall.jsonl``. This is the source of truth for recall;
        ``recall_event`` SQLite table is a derived index, see
        ``docs/structure/v3/recall.md``."""
        await self.storage.append_text(
            self._recall_key(source, session_id),
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
        location: str = "",
        location_label: str | None = None,
        last_round_update_time: str | None = None,
    ) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO sessions "
            "(session_id, source, location, location_label, cwd, "
            " created_at, synced_at, metadata, "
            " round_count, last_round_id, last_round_update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, source, location, location_label, cwd,
             created_at, synced_at,
             json.dumps(metadata, ensure_ascii=False),
             round_count, last_round_id, last_round_update_time),
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
        last_round_update_time: str | None = None,
    ) -> None:
        await self.conn.execute(
            "UPDATE sessions SET round_count = ?, last_round_id = ?, "
            "synced_at = ?, last_round_update_time = ? WHERE session_id = ?",
            (count, last_round_id, synced_at, last_round_update_time, session_id),
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

    async def get_index_health_by_endpoint(self) -> list[dict]:
        """Per-(source, location) aggregate. Used by ``GET /v3/sync/status``
        to render the per-endpoint table without the CLI having to
        re-shape totals client-side."""
        async with self.conn.execute(
            "SELECT "
            "  source, location, "
            "  COALESCE(MAX(location_label), '') AS location_label, "
            "  COUNT(*) AS sessions, "
            "  COALESCE(SUM(round_count), 0) AS rounds, "
            "  COALESCE(SUM(indexed_round_count), 0) AS indexed, "
            "  COALESCE(SUM(round_count - indexed_round_count), 0) AS missing, "
            "  SUM(CASE WHEN indexed_round_count < round_count THEN 1 ELSE 0 END) "
            "    AS degraded "
            "FROM sessions "
            "GROUP BY source, location "
            "ORDER BY source, location"
        ) as cursor:
            rows = await cursor.fetchall()
        out = []
        for r in rows:
            source = r[0]
            location = r[1] or ""
            label = r[2] or location
            out.append({
                "source": source,
                "location": location,
                "label": label,
                "endpoint": f"{source}@{label or location}",
                "sessions": int(r[3] or 0),
                "rounds": int(r[4] or 0),
                "indexed": int(r[5] or 0),
                "missing": int(r[6] or 0),
                "degraded": int(r[7] or 0),
            })
        return out

    # ─── 0.8.x: list + user-side tags ──────────────────────────────

    async def list_sessions(
        self,
        *,
        source: str | None = None,
        endpoint: str | None = None,
        cwd_prefix: str | None = None,
        tag_filters=None,  # list[TagPredicate] | None
        since: str | None = None,
        until: str | None = None,
        limit: int = 20,
    ) -> tuple[int, list[dict]]:
        """Filtered session list for ``GET /v3/sessions``.

        Returns ``(total, rows)`` — ``total`` is the unbounded match
        count (so the CLI can tell the user "23 of 1247"), ``rows`` is
        the page (``limit`` longest, ``created_at`` desc).

        Filters are AND-combined. ``endpoint`` (``<source>@<label>``)
        decomposes to source + label equality on the row's label
        (label-less rows fall back to comparing against location).

        ``tag_filters`` are :class:`memorytalk.util.tag_filter.TagPredicate`
        instances — translated to ``json_extract`` clauses via the
        shared ``tag_filter.to_sql`` so the same SQL shape lands here
        and in card list later.
        """
        from memorytalk.util.tag_filter import to_sql as _tag_sql

        clauses: list[str] = []
        params: list = []

        if source:
            clauses.append("source = ?")
            params.append(source)

        if endpoint:
            # endpoint = ``<source>@<label-or-location>``. The label is
            # display-side only; the canonical match is on
            # (source, location). When ``location_label`` is set we
            # accept either; when it isn't, fall back to location.
            ep_source, _, ep_tail = endpoint.partition("@")
            clauses.append("source = ?")
            params.append(ep_source)
            clauses.append(
                "(location_label = ? OR (location_label IS NULL AND location = ?))"
            )
            params.extend([ep_tail, ep_tail])

        if cwd_prefix:
            # SQLite has no native prefix-match operator; LIKE with a
            # literal % suffix is the conventional approach. Escape ``%``
            # and ``_`` in the user input so a path like ``foo_bar`` isn't
            # interpreted as a wildcard match.
            escaped = cwd_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("cwd LIKE ? ESCAPE '\\'")
            params.append(escaped + "%")

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
            f"SELECT COUNT(*) FROM sessions {where}", params,
        ) as cur:
            total = (await cur.fetchone())[0]

        async with self.conn.execute(
            f"SELECT * FROM sessions {where} "
            f"ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ) as cur:
            rows = await cur.fetchall()
        return total, [self._row(r) for r in rows]

    async def get_tags(self, session_id: str) -> dict | None:
        """Return the tags dict, or ``None`` if the session row is missing.
        Distinct return shape from "empty dict" so callers can tell
        404 vs "exists, no tags"."""
        async with self.conn.execute(
            "SELECT tags FROM sessions WHERE session_id = ?", (session_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return json.loads(row["tags"] or "{}")

    async def replace_tags(self, session_id: str, tags: dict) -> bool:
        """Wholesale write the tags column **and** mirror to meta.json.

        ``tags`` is assumed already validated (call
        ``util.tags.apply_patch`` first). Returns False if the
        session_id doesn't exist (so the API can return 404 without a
        separate existence check).

        Meta mirror rationale: ``meta.json`` is the file-layer audit
        copy of session metadata; ``tags`` is a user-supplied fact
        (not a derived runtime signal like ``stats``), so it belongs in
        the same persistence tier as ``metadata`` / ``round_count`` /
        ``synced_at``. Without this mirror you can't tarball-relocate
        a data root without also carrying the SQLite file.
        """
        async with self.conn.execute(
            "SELECT source FROM sessions WHERE session_id = ?", (session_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return False
        source = row["source"]

        await self.conn.execute(
            "UPDATE sessions SET tags = ? WHERE session_id = ?",
            (json.dumps(tags, ensure_ascii=False), session_id),
        )
        await self.conn.commit()

        # Mirror into meta.json. If the file is missing (degraded state
        # — sqlite row exists but the audit file was deleted), we still
        # write a partial mirror with just the tags; the next append's
        # ``_refresh_meta`` rewrites the file completely with all the
        # other fields, so self-healing is automatic.
        meta = await self.read_meta(source, session_id) or {}
        meta["tags"] = tags
        await self.write_meta(source, session_id, meta)
        return True

    @staticmethod
    def _row(row) -> dict:
        keys = row.keys()
        return {
            "session_id": row["session_id"],
            "source": row["source"],
            "location": row["location"] if "location" in keys else "",
            "location_label": row["location_label"] if "location_label" in keys else None,
            "cwd": row["cwd"],
            "created_at": row["created_at"],
            "synced_at": row["synced_at"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "tags": json.loads(row["tags"] or "{}") if "tags" in keys else {},
            "round_count": row["round_count"],
            "last_round_id": row["last_round_id"],
            "last_round_update_time": row["last_round_update_time"] if "last_round_update_time" in keys else None,
            "indexed_round_count": row["indexed_round_count"] if "indexed_round_count" in keys else 0,
            "last_index_error": row["last_index_error"] if "last_index_error" in keys else None,
            "last_index_attempted_at": row["last_index_attempted_at"] if "last_index_attempted_at" in keys else None,
        }

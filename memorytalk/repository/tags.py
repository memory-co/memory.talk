"""SubjectTagsRepo — kv tags on session/card subjects (SQLite-only).

Single ``tags`` table with ``type`` field discriminator, mirrors the
``links`` table style (id-prefix is the truth, ``type`` is denormalized
for query clarity + index efficiency).

Key shape: ``(subject_id, key)`` is the primary key; ``seq`` tracks
insertion order so the response can render keys in the order they were
first added.

This repo only touches SQLite. The on-disk ``tags.json`` mirror is
written by ``TagService`` after each mutation (it owns the file path
since path computation differs between sessions / cards).
"""
from __future__ import annotations

import aiosqlite


class SubjectTagsRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def list_for_subject(self, subject_id: str) -> list[dict]:
        """Return ``[{key, value}, ...]`` for ``subject_id`` ordered by seq."""
        async with self.conn.execute(
            "SELECT key, value FROM tags WHERE subject_id = ? ORDER BY seq ASC",
            (subject_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [{"key": r["key"], "value": r["value"]} for r in rows]

    async def upsert_one(
        self, subject_id: str, type_: str, key: str, value: str, now_iso: str,
    ) -> dict:
        """Insert or update a single (subject_id, key) row.

        Returns:
          - ``{"action": "added", "value": value}`` on insert
          - ``{"action": "updated", "value": value, "prior_value": old}`` on update
          - ``{"action": "unchanged", "value": value}`` on noop (same value)
        """
        async with self.conn.execute(
            "SELECT value FROM tags WHERE subject_id = ? AND key = ?",
            (subject_id, key),
        ) as cursor:
            existing = await cursor.fetchone()

        if existing is None:
            async with self.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM tags WHERE subject_id = ?",
                (subject_id,),
            ) as cursor:
                row = await cursor.fetchone()
            next_seq = (row[0] or 0) + 1
            await self.conn.execute(
                "INSERT INTO tags "
                "(subject_id, type, key, value, seq, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (subject_id, type_, key, value, next_seq, now_iso, now_iso),
            )
            await self.conn.commit()
            return {"action": "added", "value": value}

        prior_value = existing["value"]
        if prior_value == value:
            return {"action": "unchanged", "value": value}

        await self.conn.execute(
            "UPDATE tags SET value = ?, updated_at = ? WHERE subject_id = ? AND key = ?",
            (value, now_iso, subject_id, key),
        )
        await self.conn.commit()
        return {"action": "updated", "value": value, "prior_value": prior_value}

    async def delete_one(self, subject_id: str, key: str) -> dict | None:
        """Delete one (subject_id, key). Returns the removed row's
        ``{"key", "value"}`` or ``None`` if nothing was deleted."""
        async with self.conn.execute(
            "SELECT value FROM tags WHERE subject_id = ? AND key = ?",
            (subject_id, key),
        ) as cursor:
            existing = await cursor.fetchone()
        if existing is None:
            return None
        await self.conn.execute(
            "DELETE FROM tags WHERE subject_id = ? AND key = ?",
            (subject_id, key),
        )
        await self.conn.commit()
        return {"key": key, "value": existing["value"]}

    async def delete_subject(self, subject_id: str) -> None:
        """Cascade: drop all tags for a subject (used when subject is deleted)."""
        await self.conn.execute(
            "DELETE FROM tags WHERE subject_id = ?", (subject_id,),
        )
        await self.conn.commit()

    async def find_subjects_by_tag(
        self, key: str, value: str | None = None, type_: str | None = None,
    ) -> list[str]:
        """Inverse lookup — list subject_ids tagged with ``key`` (and
        optionally ``value`` / ``type``). Reserved for future filter API;
        not exposed yet but kept here so the contract is set."""
        sql = "SELECT subject_id FROM tags WHERE key = ?"
        params: list = [key]
        if value is not None:
            sql += " AND value = ?"
            params.append(value)
        if type_ is not None:
            sql += " AND type = ?"
            params.append(type_)
        async with self.conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def upsert_many(
        self, subject_id: str, type_: str, pairs: list[tuple[str, str]], now_iso: str,
    ) -> None:
        """Bulk replace path used by rebuild — clears the subject's tags
        then inserts each pair fresh. Order is preserved via the input
        list; seq starts at 1."""
        await self.conn.execute(
            "DELETE FROM tags WHERE subject_id = ?", (subject_id,),
        )
        for seq, (key, value) in enumerate(pairs, start=1):
            await self.conn.execute(
                "INSERT INTO tags "
                "(subject_id, type, key, value, seq, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (subject_id, type_, key, value, seq, now_iso, now_iso),
            )
        await self.conn.commit()

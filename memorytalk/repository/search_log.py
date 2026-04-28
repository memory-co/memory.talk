"""SearchLogStore — search-audit persistence (file layer + SQLite).

File layout: ``search_log/<YYYY-MM-DD>.jsonl`` (rotated daily by UTC date).
SQL: ``search_log`` table — count() drives /v2/status.searches_total.

``record()`` writes to both in one call. ``replay_files()`` reads every
JSONL line and re-inserts into SQL — used by /v2/rebuild.
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone

import aiosqlite

from memory_talk_v2.provider.storage import Storage


class SearchLogStore:
    PREFIX = "search_log"

    def __init__(self, conn: aiosqlite.Connection, storage: Storage):
        self.conn = conn
        self.storage = storage

    # ---------- file-layer keys ----------

    def _daily_key(self, when: datetime) -> str:
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        else:
            when = when.astimezone(timezone.utc)
        return f"{self.PREFIX}/{when.strftime('%Y-%m-%d')}.jsonl"

    # ---------- combined write ----------

    async def record(self, rec: dict, *, now: datetime, response_json: str) -> None:
        """Persist one search record to both the daily JSONL file and SQLite."""
        await self.storage.append_text(
            self._daily_key(now),
            json.dumps(rec, ensure_ascii=False) + "\n",
        )
        await self.conn.execute(
            "INSERT INTO search_log (search_id, query, where_dsl, top_k, created_at, response_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (rec["search_id"], rec.get("query") or "", rec.get("where"),
             int(rec.get("top_k") or 0), rec.get("created_at") or "", response_json),
        )
        await self.conn.commit()

    # ---------- rebuild path ----------

    async def replay_files(self) -> tuple[int, int]:
        """Replay every JSONL line into SQL. Returns (replayed, errors)."""
        replayed = 0
        errors = 0
        for key in await self.storage.list_subkeys(self.PREFIX):
            if not key.endswith(".jsonl"):
                continue
            text = await self.storage.read_text(key)
            if not text:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    await self.conn.execute(
                        "INSERT INTO search_log "
                        "(search_id, query, where_dsl, top_k, created_at, response_json) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (rec["search_id"], rec.get("query") or "", rec.get("where"),
                         int(rec.get("top_k") or 0), rec.get("created_at") or "",
                         json.dumps(rec, ensure_ascii=False)),
                    )
                    replayed += 1
                except Exception:
                    errors += 1
        await self.conn.commit()
        return replayed, errors

    async def apply_retention(self, days: int) -> None:
        """Delete daily JSONL files older than `days`. No-op when days <= 0."""
        if days <= 0:
            return
        cutoff = time.time() - days * 86400
        for key in await self.storage.list_subkeys(self.PREFIX):
            if not key.endswith(".jsonl"):
                continue
            # Extract date from filename "search_log/YYYY-MM-DD.jsonl"
            stem = key.rsplit("/", 1)[-1].removesuffix(".jsonl")
            try:
                file_dt = datetime.strptime(stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if file_dt.timestamp() < cutoff:
                await self.storage.delete(key)

    # ---------- SQL ----------

    async def count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM search_log") as cursor:
            row = await cursor.fetchone()
        return row[0]

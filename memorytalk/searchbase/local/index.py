"""CollectionIndex — generic vector + FTS store over arbitrary collections.

Domain-agnostic: a "collection" is just a named LanceDB table; a row is
``{id, text, vector, **fields}``. No card / round / session vocabulary
lives here — the schema for a collection is inferred from the first
row's fields and fixed thereafter.

Reuses the proven LanceDB internals (hybrid RRF search, FTS index
memoization, EMFILE recovery, version-pruning compaction) generalized to
operate over any collection rather than two hardcoded tables.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from pathlib import Path

import pyarrow as pa

# Pure helpers reused from the legacy store; they move into this file
# when provider/lancedb.py is finally deleted.
from memorytalk.provider.lancedb import (
    _in_clause, _is_emfile, _run_hybrid, _segment,
)


_log = logging.getLogger("memorytalk.searchbase.index")

_RESERVED = ("id", "text", "vector")


def _arrow_type(value) -> pa.DataType:
    """Infer a LanceDB column type from a sample field value."""
    if isinstance(value, bool):
        return pa.bool_()
    if isinstance(value, int):
        return pa.int64()
    if isinstance(value, float):
        return pa.float64()
    return pa.string()


class CollectionIndex:
    def __init__(self, db, data_dir: Path, dim: int):
        self.db = db
        self.data_dir = data_dir
        self.dim = dim
        # Per-collection "FTS index confirmed present" memo — avoids a
        # list_indices() round trip on every search once verified.
        self._fts_index_known: set[str] = set()
        # Collections we've touched — recovery/compaction iterate these.
        self._collections: set[str] = set()
        # EMFILE recovery state.
        self._recovery_lock = asyncio.Lock()
        self.emfile_recoveries: int = 0
        self.last_emfile_at_iso: str | None = None
        self.last_recovery_error: str | None = None

    @classmethod
    async def create(cls, data_dir: Path, dim: int = 384) -> "CollectionIndex":
        import lancedb
        db = await lancedb.connect_async(str(data_dir))
        self = cls(db, Path(data_dir), dim)
        try:
            self._collections.update(await self._list_tables())
        except Exception:
            pass
        return self

    async def _list_tables(self) -> list[str]:
        res = await self.db.list_tables()
        return list(res.tables if hasattr(res, "tables") else res)

    async def _exists(self, name: str) -> bool:
        return name in await self._list_tables()

    def _schema_for(self, sample: dict) -> pa.Schema:
        fields = [
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), self.dim)),
        ]
        for key, value in sample.items():
            if key in _RESERVED:
                continue
            fields.append(pa.field(key, _arrow_type(value)))
        return pa.schema(fields)

    async def _ensure_table(self, collection: str, sample: dict):
        if await self._exists(collection):
            self._collections.add(collection)
            return await self.db.open_table(collection)
        table = await self.db.create_table(
            collection, schema=self._schema_for(sample),
        )
        self._collections.add(collection)
        return table

    # ─── write ───

    async def upsert(self, collection: str, rows: list[dict]) -> None:
        """Insert/replace by ``id``. ``rows`` are ``{id, text, vector,
        **fields}``; ``text`` is segmented here (caller passes raw)."""
        if not rows:
            return
        prepared = []
        for r in rows:
            r2 = dict(r)
            r2["text"] = _segment(r.get("text") or "")
            prepared.append(r2)
        table = await self._ensure_table(collection, prepared[0])
        ids = [r["id"] for r in prepared if r.get("id") is not None]
        expr = _in_clause(ids, "id")
        if expr:
            await table.delete(expr)
        await table.add(prepared)

    async def delete(self, collection: str, ids: list[str]) -> None:
        if not ids or not await self._exists(collection):
            return
        table = await self.db.open_table(collection)
        expr = _in_clause(ids, "id")
        if expr:
            await table.delete(expr)

    async def delete_where(self, collection: str, where: str | None) -> None:
        if not where or not await self._exists(collection):
            return
        table = await self.db.open_table(collection)
        await table.delete(where)

    async def count(self, collection: str, where: str | None = None) -> int:
        if not await self._exists(collection):
            return 0
        table = await self.db.open_table(collection)
        if where:
            return await table.count_rows(where)
        return await table.count_rows()

    # ─── FTS index maintenance ───

    async def ensure_fts_index(self, collection: str) -> None:
        """Create the FTS index on ``text`` if absent. Idempotent +
        memoized (see issue #4 §4.2 — list_indices errors must bubble so
        EMFILE recovery can take over instead of compounding)."""
        if collection in self._fts_index_known:
            return
        if not await self._exists(collection):
            return
        from lancedb.index import FTS
        table = await self.db.open_table(collection)
        indices = await table.list_indices()
        for idx in indices:
            cols = getattr(idx, "columns", None) or []
            if "text" in cols:
                self._fts_index_known.add(collection)
                return
        await table.create_index(
            "text", config=FTS(base_tokenizer="whitespace", with_position=True),
            replace=False,
        )
        self._fts_index_known.add(collection)

    # ─── compaction ───

    async def optimize(self, collection: str) -> dict:
        """LanceDB VACUUM: merge fragments + prune all but the latest
        version (cleanup_older_than=0). Load-bearing against the
        append-only fragment pile that EMFILEs vector search."""
        if not await self._exists(collection):
            return {"collection": collection, "skipped": "missing"}
        table = await self.db.open_table(collection)
        stats = await table.optimize(cleanup_older_than=_dt.timedelta(0))
        return {"collection": collection, "stats": str(stats)}

    # ─── search ───

    async def search(
        self, collection: str, query: str,
        vector: list[float] | None, top_k: int, where: str | None = None,
    ) -> list[dict]:
        return await self._search_with_recovery(
            collection, query, vector, top_k, where,
        )

    async def _search_with_recovery(
        self, collection: str, query: str,
        vector: list[float] | None, top_k: int, where: str | None,
    ) -> list[dict]:
        if not await self._exists(collection):
            return []
        try:
            table = await self.db.open_table(collection)
            return await _run_hybrid(table, query, vector, top_k, where)
        except Exception as e:
            if not _is_emfile(e):
                raise
            _log.warning("EMFILE on search collection=%s; recovering", collection)
            await self._recover_from_emfile()
            if not await self._exists(collection):
                return []
            table = await self.db.open_table(collection)
            return await _run_hybrid(table, query, vector, top_k, where)

    async def _recover_from_emfile(self) -> None:
        gen_before = self.emfile_recoveries
        async with self._recovery_lock:
            if self.emfile_recoveries > gen_before:
                return
            # Re-list tables so recovery compacts the real fragment pile
            # even if the known-set went stale/empty (read-only boot, or
            # a construction-time list_tables() that failed). Without
            # this the optimize loop below could run over nothing — and
            # compaction is the step that actually relieves EMFILE.
            try:
                self._collections.update(await self._list_tables())
            except Exception:
                pass  # fall through with whatever we already know
            for collection in list(self._collections):
                try:
                    await self.optimize(collection)
                except Exception as e:
                    _log.exception(
                        "optimize during EMFILE recovery failed collection=%s",
                        collection,
                    )
                    self.last_recovery_error = f"optimize {collection}: {e}"
            try:
                import lancedb
                try:
                    await self.db.close()
                except Exception:
                    pass
                self.db = await lancedb.connect_async(str(self.data_dir))
            except Exception as e:
                _log.exception("connection reset during EMFILE recovery failed")
                self.last_recovery_error = f"reconnect: {e}"
                raise
            self.emfile_recoveries += 1
            self.last_emfile_at_iso = _dt.datetime.now(_dt.UTC).isoformat(
                timespec="seconds",
            ).replace("+00:00", "Z")

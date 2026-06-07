"""CollectionIndex — generic vector + FTS store over arbitrary collections.

Domain-agnostic: a "collection" is just a named LanceDB table; a row is
``{id, text, vector, **fields}``. No card / round / session vocabulary
lives here.

An index is a NAMED instance with a FIXED schema, declared at
construction (``collections``: collection name → {field name → type
tag}). The schema is never mutated in place — changing it means standing
up a new instance (a new name → a new directory for the local backend)
and letting the business re-fill it. So there is deliberately no
inference, no migration, no rebuild logic here.

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

from memorytalk.searchbase.local._lance_helpers import (
    _in_clause, _is_emfile, _run_hybrid, _segment,
)


_log = logging.getLogger("memorytalk.searchbase.index")

_RESERVED = ("id", "text", "vector", "_base_id", "_chunk")

# Declared field type tags → Arrow types. Unknown tag → KeyError, which
# is the right fail-fast: a typo in a collection schema is a code bug.
_TYPE_TAGS = {
    "str": pa.string(),
    "int": pa.int64(),
    "float": pa.float64(),
    "bool": pa.bool_(),
}


def _collapse_chunks(rows: list[dict]) -> list[dict]:
    """Collapse chunk rows of an auto_split collection back to one row
    per logical doc: group by ``_base_id``, keep the best-scoring chunk,
    and present its ``id`` as the logical (base) id. Chunking is thus
    invisible to the caller."""
    best: dict[str, dict] = {}
    for r in rows:
        base = r.get("_base_id") or r.get("id")
        score = float(r.get("_score", 0.0))
        if base not in best or score > float(best[base].get("_score", 0.0)):
            row = dict(r)
            row["id"] = base
            best[base] = row
    return sorted(
        best.values(), key=lambda r: float(r.get("_score", 0.0)), reverse=True,
    )


class CollectionIndex:
    def __init__(self, db, data_dir: Path, dim: int, declared: dict[str, dict]):
        self.db = db
        self.data_dir = data_dir
        self.dim = dim
        # collection name → spec ``{"fields": {field: tag}, "auto_split": bool}``,
        # fixed for this instance.
        self._declared = dict(declared)
        # Collections that chunk over-length docs across multiple rows.
        # Those rows carry hidden ``_base_id`` + ``_chunk`` columns; the
        # chunking is invisible on read (search collapses, count uses
        # chunk 0, delete keys on _base_id).
        self._auto_split: set[str] = {
            name for name, spec in self._declared.items()
            if spec.get("auto_split")
        }
        # Per-collection "FTS index confirmed present" memo — avoids a
        # list_indices() round trip on every search once verified.
        self._fts_index_known: set[str] = set()
        # Collections this instance manages — recovery/compaction iterate
        # these. Seeded from the declared set at construction.
        self._collections: set[str] = set(self._declared)
        # EMFILE recovery state.
        self._recovery_lock = asyncio.Lock()
        self.emfile_recoveries: int = 0
        self.last_emfile_at_iso: str | None = None
        self.last_recovery_error: str | None = None
        # Startup-compaction observability (surfaced via health()).
        self.last_compact_at_iso: str | None = None
        self.last_compact_error: str | None = None

    @classmethod
    async def create(
        cls, data_dir: Path, dim: int, collections: dict[str, dict],
    ) -> "CollectionIndex":
        import lancedb
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        db = await lancedb.connect_async(str(data_dir))
        self = cls(db, data_dir, dim, collections)
        # Eagerly create every declared collection's table so the schema
        # exists before the first write and search-before-write works.
        existing = set(await self._list_tables())
        for name in collections:
            if name not in existing:
                await db.create_table(name, schema=self._schema_for(name))
        return self

    async def _list_tables(self) -> list[str]:
        res = await self.db.list_tables()
        return list(res.tables if hasattr(res, "tables") else res)

    async def _exists(self, name: str) -> bool:
        return name in await self._list_tables()

    def _schema_for(self, collection: str) -> pa.Schema:
        cols = [
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), self.dim)),
        ]
        if collection in self._auto_split:
            cols.append(pa.field("_base_id", pa.string()))
            cols.append(pa.field("_chunk", pa.int32()))
        for name, tag in self._declared[collection].get("fields", {}).items():
            if name in _RESERVED:
                continue
            cols.append(pa.field(name, _TYPE_TAGS[tag]))
        return pa.schema(cols)

    # ─── write ───

    async def upsert(self, collection: str, rows: list[dict]) -> None:
        """Insert/replace ``rows`` (``{id, text, vector, **fields}``;
        ``text`` segmented here). For auto_split collections the replace
        key is ``_base_id`` (a logical doc owns all its chunk rows); for
        plain collections it's ``id``."""
        if not rows:
            return
        prepared = []
        for r in rows:
            r2 = dict(r)
            r2["text"] = _segment(r.get("text") or "")
            prepared.append(r2)
        table = await self.db.open_table(collection)
        if collection in self._auto_split:
            keys = list({r["_base_id"] for r in prepared if r.get("_base_id") is not None})
            expr = _in_clause(keys, "_base_id")
        else:
            keys = [r["id"] for r in prepared if r.get("id") is not None]
            expr = _in_clause(keys, "id")
        if expr:
            await table.delete(expr)
        await table.add(prepared)

    async def delete(self, collection: str, ids: list[str]) -> None:
        if not ids or not await self._exists(collection):
            return
        table = await self.db.open_table(collection)
        # ids are logical doc ids; for auto_split they key on _base_id so
        # all of a doc's chunks are removed.
        column = "_base_id" if collection in self._auto_split else "id"
        expr = _in_clause(ids, column)
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
        # Count LOGICAL docs: for auto_split, only chunk 0 (one per doc).
        if collection in self._auto_split:
            where = f"({where}) AND _chunk = 0" if where else "_chunk = 0"
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

    async def compact_all(self) -> None:
        """Best-effort compaction of every known collection. Run as a
        one-shot background task at instance startup so a restart always
        grinds down the append-only fragment pile (the "restart always
        compacts" guarantee that keeps vector search off the fd ceiling)."""
        try:
            self._collections.update(await self._list_tables())
        except Exception:
            pass
        self.last_compact_at_iso = _dt.datetime.now(_dt.UTC).isoformat(
            timespec="seconds",
        ).replace("+00:00", "Z")
        compact_error: str | None = None
        for collection in list(self._collections):
            try:
                result = await self.optimize(collection)
                _log.info("startup compaction done %s", result)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.exception(
                    "startup compaction failed collection=%s", collection,
                )
                compact_error = f"compact {collection}: {e}"
        self.last_compact_error = compact_error

    # ─── search ───

    async def search(
        self, collection: str, query: str,
        vector: list[float] | None, top_k: int, where: str | None = None,
    ) -> list[dict]:
        rows = await self._search_with_recovery(
            collection, query, vector, top_k, where,
        )
        if collection in self._auto_split:
            rows = _collapse_chunks(rows)
        return rows

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
            # even if the known-set went stale. Compaction is the step
            # that actually relieves EMFILE.
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

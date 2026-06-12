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
memoization) generalized to operate over any collection rather than two
hardcoded tables.

Self-maintenance (periodic compaction + EMFILE recovery + observability
counters) lives in :mod:`memorytalk.searchbase.local.maintenance` —
this file only exposes the *low-level* ops maintenance needs:
``optimize(collection)``, ``reset_connection()``, ``known_collections``,
``refresh_known_collections()``. Policy (when to compact, EMFILE
fallback, who counts what) is the Maintenance class's job.
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path

import pyarrow as pa

from memorytalk.searchbase.local.util import (
    RESERVED_COLUMNS, TYPE_TAGS,
    collapse_chunks, in_clause, is_emfile, run_hybrid, segment,
)


_log = logging.getLogger("memorytalk.searchbase.index")


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
        # Collections this instance manages — maintenance iterates these.
        # Seeded from the declared set at construction; refreshed from
        # ``_list_tables()`` via ``refresh_known_collections()``.
        self._collections: set[str] = set(self._declared)
        # Maintenance back-reference. Wired by ``LocalSearchBackend.create``
        # immediately after the index is built; ``_search_with_recovery``
        # delegates the EMFILE branch through this. ``None`` means no
        # maintenance is attached (degraded: EMFILEs re-raise instead of
        # auto-recovering).
        self._maintenance = None

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
            if name in RESERVED_COLUMNS:
                continue
            cols.append(pa.field(name, TYPE_TAGS[tag]))
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
            r2["text"] = segment(r.get("text") or "")
            prepared.append(r2)
        table = await self.db.open_table(collection)
        if collection in self._auto_split:
            keys = list({r["_base_id"] for r in prepared if r.get("_base_id") is not None})
            expr = in_clause(keys, "_base_id")
        else:
            keys = [r["id"] for r in prepared if r.get("id") is not None]
            expr = in_clause(keys, "id")
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
        expr = in_clause(ids, column)
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
        # replace=True, NOT False: when the index's files are partially
        # missing on disk (0.8.x EMFILE-era partial writes),
        # list_indices() silently OMITS the broken index while its name
        # still occupies the manifest — the loop above concludes
        # "absent", and create(replace=False) then hits "Index name
        # 'text_idx' already exists", turning every search into a 500
        # with no way to self-heal. replace=True rebuilds the broken
        # index in place; for a truly-absent index it behaves the same
        # as replace=False. (1.0.0 upgrade incident; 0.8.1 always used
        # replace=True. See tests/searchbase/local/fts_self_heal/.)
        await table.create_index(
            "text", config=FTS(base_tokenizer="whitespace", with_position=True),
            replace=True,
        )
        self._fts_index_known.add(collection)

    # ─── low-level maintenance ops ───
    #
    # Policy (when to compact, how to recover from EMFILE, what to
    # count) lives in ``searchbase/local/maintenance.py``; what's here
    # is just the LanceDB-intimate ops it needs.

    @property
    def known_collections(self) -> set[str]:
        """Collections this index has ever seen — declared at construction
        plus anything discovered via ``refresh_known_collections``. Read
        by Maintenance to iterate compaction targets."""
        return self._collections

    async def refresh_known_collections(self) -> None:
        """Refresh ``known_collections`` from the live table list.
        Tolerates ``_list_tables`` failure (caller is typically on a
        maintenance hot path and should fall through with whatever's
        already in the set)."""
        try:
            self._collections.update(await self._list_tables())
        except Exception:
            pass

    async def optimize(self, collection: str) -> dict:
        """LanceDB VACUUM for one collection: merge fragments + prune
        all but the latest version (``cleanup_older_than=0``). Returns
        a small stats dict for the caller's log; no-op (returns
        ``{skipped: "missing"}``) if the collection's table doesn't
        exist on disk yet."""
        if not await self._exists(collection):
            return {"collection": collection, "skipped": "missing"}
        table = await self.db.open_table(collection)
        stats = await table.optimize(cleanup_older_than=_dt.timedelta(0))
        return {"collection": collection, "stats": str(stats)}

    async def reset_connection(self) -> None:
        """Close the LanceDB connection and reopen it.

        Load-bearing in EMFILE recovery: compaction alone reclaims
        files on disk but the in-process readers still hold the old
        file descriptors. Only ``connect_async`` releases them. After
        this call, the next ``open_table`` returns a fresh reader
        against the freshly-merged on-disk state.
        """
        import lancedb
        try:
            await self.db.close()
        except Exception:
            pass  # already closed / unsupported — best effort
        self.db = await lancedb.connect_async(str(self.data_dir))

    def attach_maintenance(self, maintenance) -> None:
        """Wire the Maintenance back-reference. Called once by
        ``LocalSearchBackend.create`` after instantiating both objects;
        no-op for fresh-build paths that don't need EMFILE recovery."""
        self._maintenance = maintenance

    # ─── search ───

    async def search(
        self, collection: str, query: str,
        vector: list[float] | None, top_k: int, where: str | None = None,
    ) -> list[dict]:
        rows = await self._search_with_recovery(
            collection, query, vector, top_k, where,
        )
        if collection in self._auto_split:
            rows = collapse_chunks(rows)
        return rows

    async def _search_with_recovery(
        self, collection: str, query: str,
        vector: list[float] | None, top_k: int, where: str | None,
    ) -> list[dict]:
        """Run a hybrid query with EMFILE auto-recovery.

        On EMFILE, delegate to :class:`Maintenance` (one subsystem owns
        the lock + the reconnect + the counters) and then retry the
        query exactly once. A second EMFILE propagates — at that point
        the in-process recovery can't fix the underlying fd-budget vs
        fragment-count mismatch, and operator action is required.

        If no Maintenance is attached (degraded init), EMFILEs
        re-raise as-is — better a loud failure than a silent partial
        result on a broken backend.
        """
        if not await self._exists(collection):
            return []
        try:
            table = await self.db.open_table(collection)
            return await run_hybrid(table, query, vector, top_k, where)
        except Exception as e:
            if not is_emfile(e):
                raise
            if self._maintenance is None:
                # No Maintenance wired — let the caller see the EMFILE
                # rather than mask it with a broken retry.
                raise
            _log.warning(
                "EMFILE on search collection=%s; delegating to maintenance",
                collection,
            )
            await self._maintenance.recover_from_emfile()
            if not await self._exists(collection):
                return []
            table = await self.db.open_table(collection)
            return await run_hybrid(table, query, vector, top_k, where)

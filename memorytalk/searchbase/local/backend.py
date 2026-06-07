"""LocalSearchBackend — embedding + CollectionIndex behind the port.

Owns the embedder, the generic CollectionIndex, and a Maintenance
subsystem (compaction loop + EMFILE recovery + observability). Maps
generic Docs onto generic ``{id, text, vector, **fields}`` rows. There
is deliberately NO card / round / session vocabulary here —
``collection`` is an opaque string and every collection flows through
the same code path.

Self-management is delegated to :class:`Maintenance` (one file owns it)
rather than spread across this module's ``_maintenance_loop`` and
``CollectionIndex``'s recovery methods.
"""
from __future__ import annotations

from pathlib import Path

from memorytalk.searchbase._types import (
    Doc, Hit, IndexHealth, Query, SearchError,
)
from memorytalk.searchbase.local.index import CollectionIndex
from memorytalk.searchbase.local.maintenance import Maintenance


# Lance score/aux columns that are not stored Doc fields.
_NON_FIELD = (
    "id", "text", "vector", "_score", "_distance", "_relevance_score",
    "_base_id", "_chunk",
)


def _split_text(text: str, max_len: int) -> list[str]:
    """Fixed-size chunks of ``text`` (at most ``max_len`` chars each).
    Always returns at least one chunk."""
    text = text or ""
    if len(text) <= max_len:
        return [text]
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]


def _sql_literal(value) -> str:
    """Render a field value as a LanceDB SQL literal — quote strings
    (escaping single quotes), leave numbers bare."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _where_from_match(match: dict | None) -> str | None:
    """Generic field-equality filter. ``match`` keys are stored column
    names — the backend never interprets what they mean."""
    if not match:
        return None
    return " AND ".join(f"{k} = {_sql_literal(v)}" for k, v in match.items())


# How often the maintenance coroutine compacts fragments. 30 min trades
# a little periodic IO for bounded fragment growth between restarts.
_COMPACT_INTERVAL_SECONDS = 1800.0


class LocalSearchBackend:
    def __init__(self, index: CollectionIndex, embedder, max_text_length: int,
                 auto_split: set[str], compact_interval_seconds: float):
        self._embedder = embedder
        self._index: CollectionIndex | None = index
        self._max_text_length = max_text_length
        self._auto_split = auto_split
        self._compact_interval_seconds = compact_interval_seconds
        # Wired in ``create``. ``None`` only during the brief window
        # between __init__ and create's setup, or after ``close``.
        self._maintenance: Maintenance | None = None

    @classmethod
    async def create(
        cls, *, name: str, data_dir, dim: int, embedder,
        collections: dict[str, dict], max_text_length: int = 100_000,
        compact_interval_seconds: float = _COMPACT_INTERVAL_SECONDS,
    ) -> "LocalSearchBackend":
        """Open a named instance with a fixed declared schema. ``name``
        maps to a sub-directory of ``data_dir``, so different schema
        versions live in different directories. The returned instance is
        already running — Maintenance is started here, so periodic
        compaction + EMFILE recovery are live before the first caller."""
        index = await CollectionIndex.create(
            Path(data_dir) / name, dim=dim, collections=collections,
        )
        auto_split = {
            n for n, spec in collections.items() if spec.get("auto_split")
        }
        self = cls(
            index, embedder, max_text_length, auto_split,
            compact_interval_seconds,
        )
        # Wire maintenance: one subsystem owns the compaction loop, the
        # EMFILE recovery, and all the observability counters.
        # ``index.attach_maintenance`` lets the search hot path delegate
        # EMFILEs back through the Maintenance singleton without owning
        # any of the policy.
        self._maintenance = Maintenance(
            index, compact_interval_seconds=compact_interval_seconds,
        )
        index.attach_maintenance(self._maintenance)
        await self._maintenance.start()
        return self

    # ─── lifecycle ───

    async def close(self) -> None:
        if self._maintenance is not None:
            await self._maintenance.stop()
            self._maintenance = None
        self._index = None

    @property
    def ready(self) -> bool:
        return self._index is not None

    async def health(self) -> IndexHealth:
        """Surface Maintenance's six-field health dict directly. We
        don't add or rearrange anything here — the Maintenance class
        is the single source of truth for what self-maintenance
        reports."""
        detail: dict = (
            self._maintenance.health() if self._maintenance is not None else {}
        )
        return IndexHealth(ready=self.ready, detail=detail)

    # ─── write ───

    async def upsert(self, collection: str, docs: list[Doc]) -> None:
        if self._index is None or not docs:
            return
        if collection in self._auto_split:
            rows = await self._split_rows(docs)
        else:
            rows = await self._plain_rows(docs)
        await self._index.upsert(collection, rows)

    async def _plain_rows(self, docs: list[Doc]) -> list[dict]:
        """One row per doc; over-length is rejected (no silent loss)."""
        for d in docs:
            if len(d.text) > self._max_text_length:
                raise SearchError(
                    f"doc {d.id!r} text length {len(d.text)} exceeds "
                    f"max_text_length {self._max_text_length}"
                )
        vecs = await self._embedder.embed([d.text for d in docs])
        return [
            {"id": d.id, "text": d.text, "vector": v, **(d.fields or {})}
            for d, v in zip(docs, vecs)
        ]

    async def _split_rows(self, docs: list[Doc]) -> list[dict]:
        """Split each over-length doc into ``_chunk`` rows that share a
        ``_base_id`` (= the logical doc id). The chunking is invisible on
        read — the index collapses it back. ``id`` = ``f"{base}#{i}"``."""
        plan: list[tuple[Doc, int, str]] = []
        for d in docs:
            for i, chunk in enumerate(_split_text(d.text, self._max_text_length)):
                plan.append((d, i, chunk))
        vecs = await self._embedder.embed([chunk for _, _, chunk in plan])
        return [
            {
                "id": f"{d.id}#{i}", "_base_id": d.id, "_chunk": i,
                "text": chunk, "vector": v, **(d.fields or {}),
            }
            for (d, i, chunk), v in zip(plan, vecs)
        ]

    async def delete(self, collection: str, ids: list[str]) -> None:
        if self._index is None:
            return
        await self._index.delete(collection, ids)

    async def delete_where(self, collection: str, match: dict) -> None:
        if self._index is None:
            return
        await self._index.delete_where(collection, _where_from_match(match))

    async def count(self, collection: str, match: dict | None = None) -> int:
        if self._index is None:
            return 0
        return await self._index.count(collection, _where_from_match(match))

    # ─── read ───

    async def search(self, collection: str, query: Query) -> list[Hit]:
        if self._index is None:
            return []
        await self._index.ensure_fts_index(collection)
        qvec = (
            await self._embedder.embed_one(query.text)
            if query.text and query.text.strip() else None
        )
        rows = await self._index.search(
            collection, query.text, qvec, query.top_k,
            _where_from_match(query.filters),
        )
        return [
            Hit(
                id=r["id"],
                score=float(r.get("_score", 0.0)),
                fields={k: v for k, v in r.items() if k not in _NON_FIELD},
            )
            for r in rows
        ]

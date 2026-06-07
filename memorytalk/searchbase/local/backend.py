"""LocalSearchBackend — embedding + CollectionIndex behind the port.

Owns the embedder and the generic CollectionIndex (and, for the rounds
write path, a background maintenance coroutine). Maps generic Docs onto
generic ``{id, text, vector, **fields}`` rows. There is deliberately NO
card / round / session vocabulary here — ``collection`` is an opaque
string and every collection flows through the same code path.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from memorytalk.searchbase._types import (
    Doc, Hit, IndexHealth, Query, SearchError,
)
from memorytalk.searchbase.local.index import CollectionIndex


# Lance score/aux columns that are not stored Doc fields.
_NON_FIELD = ("id", "text", "vector", "_score", "_distance", "_relevance_score")


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


class LocalSearchBackend:
    def __init__(self, index: CollectionIndex, embedder, max_text_length: int):
        self._embedder = embedder
        self._index: CollectionIndex | None = index
        self._max_text_length = max_text_length
        self._maint_task: asyncio.Task | None = None

    @classmethod
    async def create(
        cls, *, name: str, data_dir, dim: int, embedder,
        collections: dict[str, dict], max_text_length: int = 100_000,
    ) -> "LocalSearchBackend":
        """Open a named instance with a fixed declared schema. ``name``
        maps to a sub-directory of ``data_dir``, so different schema
        versions live in different directories. The returned instance is
        already running — fd/compaction maintenance starts here."""
        index = await CollectionIndex.create(
            Path(data_dir) / name, dim=dim, collections=collections,
        )
        self = cls(index, embedder, max_text_length)
        # Own the fd/fragment maintenance: a one-shot startup compaction
        # in the background (never blocks boot). EMFILE recovery is
        # handled inline inside CollectionIndex.search.
        self._maint_task = asyncio.create_task(index.compact_all())
        return self

    # ─── lifecycle ───

    async def close(self) -> None:
        if self._maint_task is not None:
            self._maint_task.cancel()
            try:
                await self._maint_task
            except (asyncio.CancelledError, Exception):
                pass
            self._maint_task = None
        self._index = None

    @property
    def ready(self) -> bool:
        return self._index is not None

    async def health(self) -> IndexHealth:
        detail: dict = {}
        if self._index is not None:
            detail = {
                "emfile_recoveries": self._index.emfile_recoveries,
                "last_emfile_at_iso": self._index.last_emfile_at_iso,
                "last_recovery_error": self._index.last_recovery_error,
                "last_compact_at_iso": self._index.last_compact_at_iso,
                "last_compact_error": self._index.last_compact_error,
            }
        return IndexHealth(ready=self.ready, detail=detail)

    # ─── write ───

    async def upsert(self, collection: str, docs: list[Doc]) -> None:
        if self._index is None or not docs:
            return
        for d in docs:
            if len(d.text) > self._max_text_length:
                raise SearchError(
                    f"doc {d.id!r} text length {len(d.text)} exceeds "
                    f"max_text_length {self._max_text_length}"
                )
        # Batch-embed the whole list in one call (the embedder chunks
        # internally for remote API caps) rather than N round trips.
        vecs = await self._embedder.embed([d.text for d in docs])
        rows = [
            {"id": d.id, "text": d.text, "vector": v, **(d.fields or {})}
            for d, v in zip(docs, vecs)
        ]
        await self._index.upsert(collection, rows)

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

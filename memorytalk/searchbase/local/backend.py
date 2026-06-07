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


class LocalSearchBackend:
    def __init__(self, index: CollectionIndex, embedder, max_text_length: int,
                 auto_split: set[str]):
        self._embedder = embedder
        self._index: CollectionIndex | None = index
        self._max_text_length = max_text_length
        self._auto_split = auto_split
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
        auto_split = {
            n for n, spec in collections.items() if spec.get("auto_split")
        }
        self = cls(index, embedder, max_text_length, auto_split)
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

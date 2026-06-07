"""LocalSearchBackend — embedding + CollectionIndex behind the port.

Owns the embedder and the generic CollectionIndex (and, for the rounds
write path, a background maintenance coroutine). Maps generic Docs onto
generic ``{id, text, vector, **fields}`` rows. There is deliberately NO
card / round / session vocabulary here — ``collection`` is an opaque
string and every collection flows through the same code path.
"""
from __future__ import annotations

from memorytalk.searchbase import Doc, Hit, IndexHealth, Query
# NOTE: the embedder still lives under provider/ for now; it moves into
# searchbase/local/ in the file-relocation step.
from memorytalk.provider.embedding import get_embedder
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
    def __init__(self, config, index: CollectionIndex):
        self._config = config
        self._embedder = get_embedder(config)
        self._index: CollectionIndex | None = index

    @classmethod
    async def create(cls, config) -> "LocalSearchBackend":
        """Open the store + start the maintenance coroutine. The returned
        instance is already running — there is no separate ``start``."""
        index = await CollectionIndex.create(
            config.vectors_dir, dim=config.settings.embedding.dim,
        )
        self = cls(config, index)
        # TODO(rounds): start the background flush/compaction coroutine
        # here once the buffered rounds path lands.
        return self

    # ─── lifecycle ───

    async def close(self) -> None:
        # TODO(rounds): drain the buffer + stop the coroutine here.
        self._index = None

    @property
    def ready(self) -> bool:
        return self._index is not None

    async def health(self) -> IndexHealth:
        return IndexHealth(ready=self.ready)

    # ─── write ───

    async def upsert(self, collection: str, docs: list[Doc]) -> None:
        if self._index is None or not docs:
            return
        rows = []
        for d in docs:
            vec = await self._embedder.embed_one(d.text)
            rows.append({"id": d.id, "text": d.text, "vector": vec, **(d.fields or {})})
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
        qvec = await self._embedder.embed_one(query.text) if query.text else None
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

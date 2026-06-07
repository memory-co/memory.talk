"""LocalSearchBackend — embedding + LanceDB behind the SearchBackend port.

Owns the embedder, the LanceDB store and (later) the write buffer, and
maps generic Docs onto the per-collection LanceDB schemas. All the
lance-isms (``_segment`` chunking, ``ensure_fts_index``, table-name
constants, ``optimize``) stay inside here — callers only ever see
collections of Docs.
"""
from __future__ import annotations

from memorytalk.searchbase import Doc, Hit, IndexHealth, Query
# NOTE: embedding + lancedb still live under provider/ for now; they get
# physically moved into searchbase/local/ in the refactor step.
from memorytalk.provider.embedding import get_embedder
from memorytalk.provider.lancedb import LanceStore


# Generic collection name → LanceDB table. The business layer passes
# these strings; the backend is what knows they map to lance tables.
_COLLECTION_CARDS = "cards"
_COLLECTION_ROUNDS = "rounds"


class LocalSearchBackend:
    def __init__(self, config, vectors: LanceStore):
        self._config = config
        self._embedder = get_embedder(config)
        self._vectors: LanceStore | None = vectors

    @classmethod
    async def create(cls, config) -> "LocalSearchBackend":
        """Open the store + start the maintenance coroutine. The returned
        instance is already running — there is no separate ``start``."""
        vectors = await LanceStore.create(
            config.vectors_dir, dim=config.settings.embedding.dim,
        )
        self = cls(config, vectors)
        # TODO(rounds): start the background flush/compaction coroutine
        # here once the buffered rounds path lands.
        return self

    # ─── lifecycle ───

    async def close(self) -> None:
        # TODO(rounds): drain the buffer + stop the coroutine here.
        self._vectors = None

    @property
    def ready(self) -> bool:
        return self._vectors is not None

    async def health(self) -> IndexHealth:
        return IndexHealth(ready=self.ready)

    # ─── write ───

    async def upsert(self, collection: str, docs: list[Doc]) -> None:
        if self._vectors is None:
            return
        if collection == _COLLECTION_CARDS:
            for d in docs:
                vec = await self._embedder.embed_one(d.text)
                await self._vectors.add_card(d.id, d.text, vec)
            return
        raise NotImplementedError(collection)

    async def delete(self, collection: str, ids: list[str]) -> None:
        raise NotImplementedError

    async def delete_where(self, collection: str, match: dict) -> None:
        raise NotImplementedError

    # ─── read ───

    async def search(self, collection: str, query: Query) -> list[Hit]:
        if self._vectors is None:
            return []
        if collection == _COLLECTION_CARDS:
            await self._vectors.ensure_fts_index(self._vectors.CARDS)
            qvec = await self._embedder.embed_one(query.text) if query.text else None
            rows = await self._vectors.search_cards(
                query.text, qvec, query.top_k, None,
            )
            return [
                Hit(
                    id=r["card_id"],
                    score=float(r.get("_score", 0.0)),
                    fields={k: v for k, v in r.items()
                            if k not in ("card_id", "vector")},
                )
                for r in rows
            ]
        raise NotImplementedError(collection)

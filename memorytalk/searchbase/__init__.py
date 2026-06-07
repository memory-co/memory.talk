"""searchbase — generic, domain-agnostic search backend.

The rest of memory.talk depends ONLY on what this package exports: the
``SearchBackend`` Protocol plus the generic value types. Concrete
implementations live under ``local/`` (embedding + LanceDB) and
``server/`` (future) and are never imported by business code directly.

The contract speaks ``collection`` / ``Doc`` / ``id`` — it has no idea
what a "card", "round" or "session" is. Mapping business objects onto
collections of Docs is the service layer's job.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Doc:
    """A unit to index. ``text`` is embedded by the backend; ``fields``
    are stored alongside — used both for filtering and returned on hits.
    The caller never computes or sees vectors."""
    id: str
    text: str
    fields: dict = field(default_factory=dict)


@dataclass
class Query:
    text: str = ""
    top_k: int = 10
    filters: dict | None = None


@dataclass
class Hit:
    id: str
    score: float
    fields: dict = field(default_factory=dict)


@dataclass
class IndexHealth:
    """Backend self-report for /v3/sync/status. Shape is intentionally
    loose — different backends surface different internals."""
    ready: bool
    detail: dict = field(default_factory=dict)


class SearchError(Exception):
    """Base for searchbase failures."""


class SearchUnavailable(SearchError):
    """Backend can't serve (e.g. vector store failed to open). The API
    layer maps this to 503 rather than failing the whole server."""


class EmbedderInvalid(SearchError):
    """Boot-time embedder validation failed."""


@runtime_checkable
class SearchBackend(Protocol):
    """Generic search capability.

    A backend owns a background coroutine (started at construction) that
    handles ALL of batching, flushing, compaction and fd/EMFILE
    management internally. None of that is on this surface — callers see
    only upsert / search / delete and never think about durability
    mechanics. ``close()`` drains and shuts the coroutine down."""

    @property
    def ready(self) -> bool: ...
    async def close(self) -> None: ...
    async def health(self) -> IndexHealth: ...

    # ─── write (embed / chunk / buffer / flush are all internal) ───
    async def upsert(self, collection: str, docs: list[Doc]) -> None: ...
    async def delete(self, collection: str, ids: list[str]) -> None: ...
    async def delete_where(self, collection: str, match: dict) -> None: ...

    # ─── read ───
    async def search(self, collection: str, query: Query) -> list[Hit]: ...

    async def count(self, collection: str, match: dict | None = None) -> int:
        """Number of durably-indexed docs in ``collection`` whose stored
        fields match every key in ``match``. Reads real index state (not
        a guess) — the business uses it to learn indexing progress
        without searchbase knowing what the fields *mean*."""
        ...


async def make_search_backend(config) -> SearchBackend:
    """Composition seam — the ONLY place that picks an implementation.

    Async because constructing a backend opens its store and spins up
    its maintenance coroutine; the returned instance is already running.
    Today there's just ``local``; a future ``server`` backend gets
    selected here off config without any business code changing."""
    from memorytalk.searchbase.local.backend import LocalSearchBackend
    return await LocalSearchBackend.create(config)

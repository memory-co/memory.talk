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
from typing import Awaitable, Callable, Protocol, runtime_checkable


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


class FlushListener(Protocol):
    """Business hook for the deferred write path. The backend buffers
    upserts and flushes them in batches; when a batch lands (or fails)
    the listener is told which Docs were affected. This is how the
    domain (e.g. "session X now has N rounds indexed") stays out of the
    generic backend — the listener interprets ``doc.fields``."""

    async def on_flushed(self, collection: str, docs: list[Doc]) -> None: ...
    async def on_flush_failed(
        self, collection: str, docs: list[Doc], error: Exception
    ) -> None: ...


@runtime_checkable
class SearchBackend(Protocol):
    # ─── lifecycle ───
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    @property
    def ready(self) -> bool: ...
    async def compact(self) -> None: ...
    async def flush(self) -> int: ...
    async def health(self) -> IndexHealth: ...
    def set_flush_listener(self, listener: FlushListener | None) -> None: ...

    # ─── write (embed / chunk / buffer are all internal) ───
    async def upsert(self, collection: str, docs: list[Doc]) -> None: ...
    async def delete(self, collection: str, ids: list[str]) -> None: ...
    async def delete_where(self, collection: str, match: dict) -> None: ...

    # ─── read ───
    async def search(self, collection: str, query: Query) -> list[Hit]: ...


def make_search_backend(config) -> SearchBackend:
    """Composition seam — the ONLY place that picks an implementation.

    Today there's just ``local``. A future ``server`` provider gets
    selected here off config without any business code changing."""
    from memorytalk.searchbase.local.backend import LocalSearchBackend
    return LocalSearchBackend(config)

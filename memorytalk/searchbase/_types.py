"""searchbase value types + the SearchBackend port.

Kept in their own module (not ``__init__``) so the package can also
export the concrete backend class without a circular import.

These are pydantic models for consistency with the rest of the codebase
(``schemas/``). They're plain carriers — no card/round/session meaning
lives here.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Doc(BaseModel):
    """A unit to index. ``text`` is embedded by the backend; ``fields``
    are stored alongside — used both for filtering and returned on hits.
    The caller never computes or sees vectors."""
    id: str
    text: str
    fields: dict = Field(default_factory=dict)


class Query(BaseModel):
    text: str = ""
    top_k: int = 10
    filters: dict | None = None


class Hit(BaseModel):
    id: str
    score: float
    fields: dict = Field(default_factory=dict)


class IndexHealth(BaseModel):
    """Backend self-report for /v3/sync/status. Shape is intentionally
    loose — different backends surface different internals."""
    ready: bool
    detail: dict = Field(default_factory=dict)


class SearchError(Exception):
    """Base for searchbase failures."""


class SearchUnavailable(SearchError):
    """Backend can't serve (e.g. vector store failed to open). The API
    layer maps this to 503 rather than failing the whole server."""


class EmbedderInvalid(SearchError):
    """Boot-time embedder validation failed."""


@runtime_checkable
class AdminBackend(Protocol):
    """Low-level schema operations on a SearchBackend.

    Used by the ``memorytalk.migration`` framework to evolve schemas in
    place. Deliberately separate from the read/write hot path so the
    public ``SearchBackend`` stays small and domain-agnostic. Business
    service code should NEVER reach for ``admin()`` — only the migration
    runner does.
    """

    async def list_collections(self) -> list[str]: ...
    async def list_columns(self, collection: str) -> list[str]: ...

    async def add_column(
        self,
        collection: str,
        column: str,
        type_: str,
        *,
        default: object | None = None,
        sql_compute: str | None = None,
    ) -> None:
        """Add a column. ``sql_compute`` is a SQL expression evaluated
        per existing row to populate the new column (e.g. for derived
        ids). ``default`` is a literal value used when ``sql_compute``
        is None. ``type_`` is one of ``str / int / float / bool``."""

    async def rename_column(
        self, collection: str, old: str, new: str,
    ) -> None: ...

    async def drop_column(
        self, collection: str, column: str,
    ) -> None: ...

    async def create_collection(
        self, name: str, schema: dict,
    ) -> None:
        """Create a new collection with the given schema spec
        (same shape as ``CollectionIndex.create``'s ``collections`` arg
        entry: ``{"fields": {...}, "auto_split": bool}``)."""

    async def drop_collection(self, name: str) -> None: ...


@runtime_checkable
class SearchBackend(Protocol):
    """Generic search capability — a named, fixed-schema index.

    An instance is opened with a declared schema; in-place schema
    evolution happens through ``admin()`` driven by the
    ``memorytalk.migration`` framework, NOT through the hot path here.
    Callers see only upsert / search / count / delete and never think
    about how vectors are stored, batched or flushed. ``close()``
    shuts the instance down.
    """

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
        fields match every key in ``match``."""
        ...

    # ─── admin (migration framework only) ───
    def admin(self) -> AdminBackend:
        """Low-level schema admin port. Used by ``memorytalk.migration``
        to evolve schemas in place; business service code never calls
        this."""
        ...

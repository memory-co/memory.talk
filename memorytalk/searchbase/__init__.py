"""searchbase — generic, domain-agnostic search backend.

The rest of memory.talk depends ONLY on what this package exports: the
``SearchBackend`` port, the value types, and the concrete backend
class(es). The contract speaks ``collection`` / ``Doc`` / ``id`` — it has
no idea what a "card", "round" or "session" is; mapping business objects
onto collections of Docs is the service layer's job.

Construction is an async classmethod on the backend class (opening the
store + starting the maintenance coroutine need ``await``):

    backend = await LocalSearchBackend.create(
        data_dir=..., dim=384, embedder=...,
        collections={"cards": {"fields": {}}},
    )

Schema evolution (column adds, renames, etc.) is driven by the
separate ``memorytalk.migration`` framework via ``backend.admin()``.

The settings → args mapping (and the eventual local/server choice) lives
in the business layer, not here — searchbase takes plain values and never
reads a Config.
"""
from memorytalk.searchbase._types import (
    AdminBackend,
    Doc,
    EmbedderInvalid,
    Hit,
    IndexHealth,
    Query,
    SearchBackend,
    SearchError,
    SearchUnavailable,
)
from memorytalk.searchbase.local.backend import LocalSearchBackend

__all__ = [
    "Doc",
    "Query",
    "Hit",
    "IndexHealth",
    "SearchError",
    "SearchUnavailable",
    "EmbedderInvalid",
    "AdminBackend",
    "SearchBackend",
    "LocalSearchBackend",
]

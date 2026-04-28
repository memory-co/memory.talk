"""Persistence layer — each per-domain Store owns BOTH file ops (via Storage)
and SQL ops (via aiosqlite). Services inject `SQLiteStore` and access each
noun's store as an attribute: `db.sessions`, `db.cards`, `db.links`,
`db.search_log`.
"""
from memorytalk.repository.cards import CardStore
from memorytalk.repository.links import LinkStore
from memorytalk.repository.schema import init_schema
from memorytalk.repository.search_log import SearchLogStore
from memorytalk.repository.sessions import SessionStore
from memorytalk.repository.store import SQLiteStore


__all__ = [
    "SQLiteStore",
    "SessionStore", "CardStore", "LinkStore", "SearchLogStore",
    "init_schema",
]

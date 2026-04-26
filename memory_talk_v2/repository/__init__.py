"""Persistence layer — each per-domain Store owns BOTH file ops (via Storage)
and SQL ops (via aiosqlite). Services inject `SQLiteStore` and access each
noun's store as an attribute: `db.sessions`, `db.cards`, `db.links`,
`db.search_log`.
"""
from memory_talk_v2.repository.cards import CardStore
from memory_talk_v2.repository.links import LinkStore
from memory_talk_v2.repository.schema import init_schema
from memory_talk_v2.repository.search_log import SearchLogStore
from memory_talk_v2.repository.sessions import SessionStore
from memory_talk_v2.repository.store import SQLiteStore


__all__ = [
    "SQLiteStore",
    "SessionStore", "CardStore", "LinkStore", "SearchLogStore",
    "init_schema",
]

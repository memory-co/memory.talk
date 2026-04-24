"""Async repository layer over aiosqlite. Services inject `SQLiteStore`
and access each noun's repo as an attribute (`db.cards`, `db.sessions`, ...).
"""
from memory_talk_v2.repository.cards import CardRepo
from memory_talk_v2.repository.links import LinkRepo
from memory_talk_v2.repository.schema import init_schema
from memory_talk_v2.repository.search_log import SearchLogRepo
from memory_talk_v2.repository.sessions import SessionRepo
from memory_talk_v2.repository.store import SQLiteStore


__all__ = [
    "SQLiteStore",
    "SessionRepo", "CardRepo", "LinkRepo", "SearchLogRepo",
    "init_schema",
]

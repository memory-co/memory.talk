"""Shared fixtures for v4 repository scenarios.

``v4db`` gives a temp SQLite (v4 DDL applied, row_factory=Row) plus a
LocalStorage file root. Each scenario constructs the store(s) it needs
from ``v4db.conn`` / ``v4db.storage`` via a small per-scenario fixture --
keeping scenarios decoupled so each store task is independently testable.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from memorytalk.config import Config
from memorytalk.provider.storage import LocalStorage
from memorytalk.repository.store import SQLiteStore
from memorytalk.repository.card_schema import create_card_schema


@pytest.fixture
async def v4db(data_root):
    config = Config(data_root)
    config.ensure_dirs()
    conn = await SQLiteStore.open_connection(config.db_path)  # sets row_factory=Row
    await create_card_schema(conn)
    storage = LocalStorage(config.data_root)
    try:
        yield SimpleNamespace(conn=conn, storage=storage)
    finally:
        await conn.close()

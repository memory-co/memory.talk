"""v2 fresh-install: SQLite schema snapshot.

A v2 database = the v1 snapshot + the explore delta. Rather than copy v1's
full DDL, we run the v1 snapshot and then apply the (idempotent) v1→v2
``up_database`` delta — one source of truth for "what v2 adds".
"""
from __future__ import annotations

import aiosqlite

from memorytalk.migrations.v1 import init_database as _v1
from memorytalk.migrations.v2 import up_database as _delta


async def run(conn: aiosqlite.Connection) -> None:
    """Apply the v2 snapshot to a fresh ``conn``."""
    await _v1.run(conn)       # v1 tables + indexes
    await _delta.run(conn)    # explores table + explore columns + indexes

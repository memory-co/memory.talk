"""v4 fresh-install: full SQLite schema snapshot AS OF v4.

= the v3 snapshot (sessions / insights / explores / recall_event /
search_log) + the 5 v4 card tables. Composed by delegating to the v3
init and then layering the v4 schema on top, so the two never drift.
"""
from __future__ import annotations

from memorytalk.migrations.v3 import init_database as v3_init
from memorytalk.repository.v4.schema import create_v4_schema


async def run(conn, *, data_root=None) -> None:
    await v3_init.run(conn, data_root=data_root)   # insight schema + infra
    await create_v4_schema(conn)                    # + v4 card tables

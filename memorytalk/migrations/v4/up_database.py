"""v4 upgrade: create the 5 v4 card tables.

The card subsystem's data layer (built in the data-foundation plan) lives
in ``repository/v4/schema.py`` as the single source of truth; this
migration just runs it. Tables: ``cards`` (issue) / ``positions`` (claim)
/ ``reviews`` (stance on a Position) / ``card_links`` / ``card_sessions``.
These names were freed by migration ``v3`` (v3 card → insight rename +
``reviews`` DROP). No FOREIGN KEY anywhere (repo hard rule).
"""
from __future__ import annotations

from memorytalk.repository.v4.schema import create_v4_schema


async def run(conn, *, data_root=None) -> None:
    """v3 → v4. Idempotent (CREATE TABLE IF NOT EXISTS)."""
    await create_v4_schema(conn)

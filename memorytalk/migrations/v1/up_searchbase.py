"""v1 upgrade: bring 0.8.x searchbase (LanceDB) tables up to v1.

What 0.8.x looked like and what v1 expects:

- ``cards`` v0.8.x:  ``{card_id, text, vector}``
  ``cards`` v1:      ``{id, text, vector}``
  → rename ``card_id`` → ``id``.

- ``rounds`` v0.8.x: ``{session_id, idx, role, text, vector}``
  ``rounds`` v1:     ``{id, _base_id, _chunk, session_id, idx, role,
                        text, vector}``
  → add ``id`` (``= session_id || ':' || CAST(idx AS STRING)`` — matches
    :func:`searchbase_schema.round_doc_id`), ``_base_id`` (same), and
    ``_chunk`` (= 0 — every existing 0.8.x row was a single chunk;
    auto_split applies to new long-text writes going forward).

Each step is gated on "is the destination state already there?" so
re-runs (including after a partial failure) are no-ops. If the
collection itself is missing the step is skipped — fresh installs go
through ``init_searchbase`` instead.
"""
from __future__ import annotations

from memorytalk.searchbase import AdminBackend


async def run(admin: AdminBackend, *, data_root=None) -> None:
    collections = set(await admin.list_collections())

    if "cards" in collections:
        cols = set(await admin.list_columns("cards"))
        if "card_id" in cols and "id" not in cols:
            await admin.rename_column("cards", "card_id", "id")

    if "rounds" in collections:
        cols = set(await admin.list_columns("rounds"))
        # Cast idx → STRING for concatenation with session_id; the
        # admin layer wraps the whole expression in its own type-CAST
        # so this is just an inner cast for ``||`` operand typing.
        id_expr = "session_id || ':' || CAST(idx AS STRING)"
        if "id" not in cols:
            await admin.add_column("rounds", "id", "str", sql_compute=id_expr)
        if "_base_id" not in cols:
            await admin.add_column(
                "rounds", "_base_id", "str", sql_compute=id_expr,
            )
        if "_chunk" not in cols:
            await admin.add_column("rounds", "_chunk", "int", default=0)

"""v3 fresh-install: searchbase (LanceDB) snapshot.

Identical to v2 — the v3 rename (cards → insight) added no LanceDB
collections and no embedding changes (it's SQLite-only). Re-use v2's
snapshot so there's nothing to keep in sync.
"""
from memorytalk.migrations.v2.init_searchbase import run  # noqa: F401  (re-export)

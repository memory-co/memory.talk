"""v2 fresh-install: searchbase (LanceDB) snapshot.

Identical to v1 — explore added no collections and no embedding changes
(it's SQLite-only: cards/reviews gained an ``explore_id`` column). Re-use
v1's snapshot so there's nothing to keep in sync.
"""
from memorytalk.migrations.v1.init_searchbase import run  # noqa: F401  (re-export)

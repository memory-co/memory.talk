"""v4 fresh-install: searchbase snapshot.

Identical to v3 — v4 adds no LanceDB collections yet (SQLite-only; the
``cards``/``positions`` embedding collections are a later plan). Re-use
v3's snapshot so there's nothing to keep in sync.
"""
from memorytalk.migrations.v3.init_searchbase import run  # noqa: F401  (re-export)

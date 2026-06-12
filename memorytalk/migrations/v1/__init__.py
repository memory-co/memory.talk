"""v1 — first version under the migration framework.

Snapshots and 0.8.x → v1 deltas for both subsystems:

- ``init_database`` / ``init_searchbase``: schema at v1 (idempotent),
  used by the fresh-install path.
- ``up_database`` / ``up_searchbase``: 0.8.x → v1 deltas
  (SQLite column adds + LanceDB rename + computed columns),
  used by the upgrade path.

Both ups are idempotent (each step gated on "does this state already
exist?") so a crash + restart doesn't double-apply.
"""

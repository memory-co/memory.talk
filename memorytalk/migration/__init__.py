"""memorytalk.migration — schema-evolution runner.

The framework that brings persistent state (SQLite + searchbase) from
whatever shape it has on disk up to what the current code declares.
The version content lives in ``memorytalk.migrations`` (peer package);
this module is the runner that discovers, picks a mode, and applies.

Design: docs/works/v3/migration.md.

Public surface:

    runner = MigrationRunner(
        db_conn=...,
        admin=backend.admin(),
        state_path=config.migrations_state_path,
    )
    summary = await runner.run()
"""
from memorytalk.migration._types import Mode, Summary
from memorytalk.migration.runner import MigrationRunner
from memorytalk.migration.state import MigrationState

__all__ = ["MigrationRunner", "MigrationState", "Mode", "Summary"]

"""MigrationRunner — discover, decide, apply.

Decision tree (see docs/works/v3/migration.md §"Runner 内部逻辑"):

    if state file is empty:
        if existing data on disk → upgrade_from_zero
        else                     → init_latest
    else                         → catch_up

For ``init_latest`` the runner only invokes the **latest** version's
``init_*.py``; older inits are kept in the repo as schema snapshots but
never executed. For ``catch_up`` / ``upgrade_from_zero`` the runner
applies the ``up_*.py`` files for each missing version in order.

State is flushed atomically after every successful per-subsystem
migration, so a crash mid-way leaves the previous successful work
recorded; the resume starts from the next pending one.
"""
from __future__ import annotations

import datetime as _dt
import logging
import time
from pathlib import Path

from memorytalk.migration._types import Mode, Summary
from memorytalk.migration.discover import (
    discover_versions, import_migration_module,
)
from memorytalk.migration.state import MigrationState


_log = logging.getLogger("memorytalk.migration")

_SUBSYSTEMS = ("database", "searchbase")


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(
        timespec="seconds",
    ).replace("+00:00", "Z")


class MigrationRunner:
    def __init__(
        self,
        *,
        db_conn=None,              # aiosqlite.Connection (for database migrations)
        admin=None,                # AdminBackend (for searchbase migrations)
        state_path: Path | str,
        data_root: Path | str | None = None,
        existing_install: bool | None = None,
        migrations_pkg: str = "memorytalk.migrations",
    ):
        """``data_root`` is consulted only as a fallback for the
        upgrade_from_zero detection heuristic (does ``memory.db`` /
        ``vectors/`` exist?). Callers that know the answer should pass
        ``existing_install`` explicitly — the heuristic gets fooled
        when the caller opened the SQLite conn or the searchbase
        backend before constructing the runner, because both create
        files. ``None`` falls back to the heuristic.

        Either handle may be ``None``: subsystems without a handle are
        skipped this run (state stays at the previous mark, so the next
        boot — which presumably has the handle — picks them up). The
        common case is searchbase failing to open at boot; we still want
        to bring the SQLite side forward."""
        self._db_conn = db_conn
        self._admin = admin
        self._state = MigrationState(state_path)
        self._data_root = Path(data_root) if data_root else None
        self._existing_install_override = existing_install
        self._migrations_pkg = migrations_pkg

    async def run(self) -> Summary:
        applied = self._state.load()
        applied_set = {
            (a["version"], a["subsystem"]) for a in applied
        }
        versions = discover_versions(self._migrations_pkg)
        if not versions:
            # No migrations declared — nothing to do.
            return Summary(mode="catch_up")
        latest = versions[-1]

        mode = await self._pick_mode(applied_set)
        active_subs = tuple(s for s in _SUBSYSTEMS if self._handle_for(s) is not None)
        _log.info(
            "migration: mode=%s versions=%s state_has=%d active=%s",
            mode, versions, len(applied_set), ",".join(active_subs),
        )

        summary = Summary(mode=mode)
        if mode == "init_latest":
            for sub in active_subs:
                await self._run_method(latest, sub, "init", summary)
                # Mark ALL versions as applied — we used the latest's
                # init, so we're already at latest.
                for v in versions:
                    if not self._state.is_applied(v, sub):
                        self._state.mark(
                            v, sub, method="init",
                            applied_at=_utc_iso(), duration_ms=0,
                        )
                self._state.save()
        else:
            # catch_up or upgrade_from_zero — same code path: apply
            # ups for each version after the highest currently applied
            # (None when applied_set is empty).
            for sub in active_subs:
                current = self._state.highest_applied(sub, versions)
                pending = _versions_after(current, versions)
                for v in pending:
                    await self._run_method(v, sub, "up", summary)
                    self._state.save()

        return summary

    def _handle_for(self, subsystem: str):
        return self._db_conn if subsystem == "database" else self._admin

    # ─── internals ────────────────────────────────────────────────

    async def _pick_mode(self, applied_set: set[tuple[str, str]]) -> Mode:
        if applied_set:
            return "catch_up"
        if self._existing_install_override is not None:
            return (
                "upgrade_from_zero" if self._existing_install_override
                else "init_latest"
            )
        if await self._looks_like_existing_install():
            return "upgrade_from_zero"
        return "init_latest"

    async def _looks_like_existing_install(self) -> bool:
        """True when there's data that pre-dates this migration system.

        Two strong signals; either suffices:

        1. The SQLite DB already has user tables (the previous
           ``init_schema`` ran in some prior 0.x boot). We probe
           ``sqlite_master`` rather than checking ``memory.db``'s
           existence — the file gets created the moment we open the
           connection, which would fool an existence-check on a fresh
           install.
        2. The data root has a populated vectors / sessions / cards
           directory (the searchbase side could have data even with no
           SQLite — and ``vectors/`` is the load-bearing one for the
           searchbase upgrade path).
        """
        if self._db_conn is not None:
            async with self._db_conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' LIMIT 1"
            ) as cur:
                if await cur.fetchone() is not None:
                    return True
        if self._data_root is not None:
            for sub in ("vectors", "sessions", "cards"):
                d = self._data_root / sub
                if d.exists() and any(d.iterdir()):
                    return True
        return False

    async def _run_method(
        self, version: str, subsystem: str, method: str, summary: Summary,
    ) -> None:
        module = import_migration_module(
            version, subsystem, method,
            package=self._migrations_pkg,
        )
        handle = self._handle_for(subsystem)
        start = time.monotonic()
        _log.info(
            "migration: %s/%s/%s start", version, subsystem, method,
        )
        await module.run(handle, data_root=self._data_root)
        duration_ms = int((time.monotonic() - start) * 1000)
        _log.info(
            "migration: %s/%s/%s done (%d ms)",
            version, subsystem, method, duration_ms,
        )
        self._state.mark(
            version, subsystem, method=method,
            applied_at=_utc_iso(), duration_ms=duration_ms,
        )
        summary.applied.append((version, subsystem))


def _versions_after(current: str | None, versions: list[str]) -> list[str]:
    if current is None:
        return list(versions)
    try:
        idx = versions.index(current)
    except ValueError:
        # state references a version we don't have anymore — caller is
        # on a downgraded code path. Pending = nothing.
        return []
    return versions[idx + 1:]



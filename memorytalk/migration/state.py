"""Persistent state for the migration runner.

JSON file at ``data_root/migrations_state.json`` (not SQLite — the
state is a flat list of a few rows, and a JSON file is simpler:
``cat`` / ``jq`` to inspect, no schema for the state itself, no
chicken-and-egg between "create state table" and "run first
migration").

Atomic write via tmpfile + ``os.replace`` so a crash mid-write can't
leave a half-written JSON. memory.talk is single-process at boot so no
file locking is needed; the runner runs once during lifespan startup.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


_STATE_SCHEMA_VERSION = 1


class StateLoadError(RuntimeError):
    """Raised when the state file exists but is unreadable. The runner
    aborts in this case rather than silently restarting from empty —
    "I lost track of what's applied" is an operator-action moment, not
    something to paper over."""


class MigrationState:
    """In-memory + on-disk store of "which (version, subsystem)
    migrations have been applied".

    Load on construction (idempotent for missing file → empty state),
    ``mark`` records a new applied entry in memory, ``save`` flushes to
    disk via atomic replace.
    """

    def __init__(self, path: Path | str):
        self._path = Path(path)
        self._applied: list[dict] = []
        self._loaded = False

    # ─── load / save ──────────────────────────────────────────────

    def load(self) -> list[dict]:
        """Return the list of applied-migration records. Empty list
        when the file doesn't exist (= fresh install / 0.8.x upgrade).
        Raises :class:`StateLoadError` if the file exists but is
        malformed — the runner converts that into an abort."""
        if self._loaded:
            return list(self._applied)
        if not self._path.exists():
            self._applied = []
            self._loaded = True
            return []
        try:
            body = json.loads(self._path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise StateLoadError(
                f"migration state file {self._path} is unreadable: {e}"
            ) from e
        applied = body.get("applied")
        if not isinstance(applied, list):
            raise StateLoadError(
                f"migration state file {self._path} has malformed "
                f"'applied' field (expected list)"
            )
        self._applied = list(applied)
        self._loaded = True
        return list(self._applied)

    def save(self) -> None:
        """Atomic write to disk. ``load`` first (or use ``mark``) so
        the in-memory list is the source of truth for this write."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "schema_version": _STATE_SCHEMA_VERSION,
            "applied": self._applied,
        }
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(body, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, self._path)

    # ─── mutators ─────────────────────────────────────────────────

    def mark(
        self,
        version: str,
        subsystem: str,
        *,
        method: str,
        applied_at: str,
        duration_ms: int,
    ) -> None:
        """Record a successful migration. In-memory only — call
        ``save()`` to flush. The runner saves after every successful
        migration for crash-safe resumption."""
        # De-dupe: same (version, subsystem) is replaced, not stacked.
        # In practice this happens when an init_latest run marks the
        # same version a second time (defensive).
        self._applied = [
            a for a in self._applied
            if not (
                a.get("version") == version
                and a.get("subsystem") == subsystem
            )
        ]
        self._applied.append({
            "version": version,
            "subsystem": subsystem,
            "method": method,
            "applied_at": applied_at,
            "duration_ms": duration_ms,
        })

    # ─── queries ──────────────────────────────────────────────────

    def is_applied(self, version: str, subsystem: str) -> bool:
        return any(
            a.get("version") == version and a.get("subsystem") == subsystem
            for a in self._applied
        )

    def highest_applied(self, subsystem: str, versions: list[str]) -> str | None:
        """Latest ``version`` from ``versions`` that has been applied
        for ``subsystem``. ``None`` if nothing has been applied yet.
        ``versions`` is the discovered order (assumed sorted)."""
        applied = {
            a["version"] for a in self._applied
            if a.get("subsystem") == subsystem
        }
        latest = None
        for v in versions:
            if v in applied:
                latest = v
        return latest

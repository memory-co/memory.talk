"""Maintenance — searchbase/local self-management subsystem.

One file with one class. Owns:

  1. The periodic compaction loop (run-at-start + tick on interval).
  2. EMFILE recovery driven from ``CollectionIndex._search_with_recovery``.
  3. All maintenance observability counters — a single source of truth
     for ``LocalSearchBackend.health()``.

Why a separate file: previously these concerns were split across
``backend.py`` (the loop) and ``index.py`` (compaction op + recovery +
six counters), so "how does searchbase self-maintain?" required reading
two files + picking attributes out of ``__init__``. Now the answer is
``maintenance.py``.

Boundary with ``CollectionIndex``:

  - Index owns the low-level LanceDB ops: ``optimize(collection)``,
    ``reset_connection()``, ``refresh_known_collections()``, and the
    ``known_collections`` view.
  - Maintenance owns the *policy*: when to compact, how often, what to
    do on EMFILE, how to count and report.

The two communicate through public methods on the index — no private
attribute reads from the maintenance side.
"""
from __future__ import annotations

import asyncio
import logging

from memorytalk.searchbase.local.util import utc_iso


_log = logging.getLogger("memorytalk.searchbase.maintenance")


class Maintenance:
    """Self-maintenance for one :class:`CollectionIndex`.

    Lifecycle:
        ``start()`` spawns the periodic loop in the background;
        ``stop()`` cancels it and awaits it. Both are idempotent.

    Crash-safety:
        Each compaction *iteration* is wrapped in its own try/except
        so a single fluke failure (a fragment file disappeared
        mid-compact, transient IO error, ...) does NOT terminate the
        loop. The previous design had a single try around the whole
        ``while True`` — any unexpected exception silently killed
        maintenance until the next process restart.

    EMFILE recovery:
        Driven from ``CollectionIndex._search_with_recovery`` via
        ``recover_from_emfile()``. Lock-protected with a generation
        counter so N concurrent search callers hitting EMFILE drive
        the recovery exactly once between them; followers see the
        counter advanced and return immediately so their retry hits
        the post-recovery connection.
    """

    def __init__(
        self,
        index,                                  # CollectionIndex back-ref
        *,
        compact_interval_seconds: float,
    ):
        self._index = index
        self._compact_interval_seconds = compact_interval_seconds
        # ── Compaction observability ─────────────────────────────────
        self.compactions: int = 0
        self.last_compact_at_iso: str | None = None
        self.last_compact_error: str | None = None
        # ── EMFILE recovery observability ────────────────────────────
        self.emfile_recoveries: int = 0
        self.last_emfile_at_iso: str | None = None
        self.last_recovery_error: str | None = None
        # ── Concurrency ──────────────────────────────────────────────
        self._recovery_lock = asyncio.Lock()
        # ── Loop ─────────────────────────────────────────────────────
        self._loop_task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ─── lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Spawn the periodic compaction loop. Idempotent."""
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop = asyncio.Event()
        self._loop_task = asyncio.create_task(
            self._loop(), name="memorytalk.searchbase.maintenance",
        )

    async def stop(self) -> None:
        """Cancel + await the loop. Idempotent."""
        self._stop.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):
                pass
            self._loop_task = None

    # ─── periodic loop ───────────────────────────────────────────────

    async def _loop(self) -> None:
        """Run ``compact_all`` at startup, then every
        ``compact_interval_seconds`` until ``stop()`` is signaled.

        Each invocation is wrapped in its own try/except: an
        exceptional iteration is logged and skipped; the loop survives.
        """
        # Boot-time compaction — runs before the first sleep so a
        # freshly-restarted process grinds down whatever fragments
        # accumulated before the restart.
        try:
            await self.compact_all()
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("startup compact_all failed (swallowed)")

        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._compact_interval_seconds,
                )
                return  # stop signaled while we slept
            except asyncio.TimeoutError:
                pass  # interval elapsed → run a tick
            try:
                await self.compact_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("compact_all iteration failed (swallowed)")

    # ─── compaction ──────────────────────────────────────────────────

    async def compact_all(self) -> None:
        """Compact every collection the index knows about.

        Refreshes the known-set first so a recently-created collection
        is included, and so recovery still works on an index whose
        declared set has drifted from the actual table list on disk.

        Per-collection failures are recorded in ``last_compact_error``
        but never raised: a flaky collection mustn't take the whole
        loop down.
        """
        try:
            await self._index.refresh_known_collections()
        except Exception:
            # If even the refresh fails, fall through with whatever
            # collections we already knew about — better some
            # compaction than none.
            pass
        self.last_compact_at_iso = utc_iso()
        compact_error: str | None = None
        for collection in list(self._index.known_collections):
            try:
                result = await self._index.optimize(collection)
                _log.info("compaction done %s", result)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.exception(
                    "compaction failed collection=%s", collection,
                )
                compact_error = f"compact {collection}: {e}"
        # Cleared to None on a fully-successful pass — the field
        # reflects the LATEST attempt, not historical failures.
        self.last_compact_error = compact_error
        self.compactions += 1

    # ─── EMFILE recovery ─────────────────────────────────────────────

    async def recover_from_emfile(self) -> None:
        """Run compaction + connection reset under a lock so concurrent
        EMFILE callers share the work.

        The first caller through the lock advances ``emfile_recoveries``.
        Followers see it advanced and return immediately so their retry
        hits the now-reset connection without spinning a second
        identical recovery.

        Compact failures are best-effort (recorded in
        ``last_recovery_error``, but the recovery proceeds to the
        connection reset, which is the step that actually releases the
        held reader fds). Reconnect failure DOES raise: retrying on the
        stale connection would just EMFILE again.
        """
        gen_before = self.emfile_recoveries
        async with self._recovery_lock:
            if self.emfile_recoveries > gen_before:
                return  # someone else recovered while we were waiting

            try:
                await self._index.refresh_known_collections()
            except Exception:
                pass
            for collection in list(self._index.known_collections):
                try:
                    await self._index.optimize(collection)
                except Exception as e:
                    _log.exception(
                        "optimize during EMFILE recovery failed collection=%s",
                        collection,
                    )
                    self.last_recovery_error = f"optimize {collection}: {e}"

            try:
                await self._index.reset_connection()
            except Exception as e:
                _log.exception(
                    "connection reset during EMFILE recovery failed",
                )
                self.last_recovery_error = f"reconnect: {e}"
                raise

            self.emfile_recoveries += 1
            self.last_emfile_at_iso = utc_iso()

    # ─── observability ───────────────────────────────────────────────

    def health(self) -> dict:
        """Returns the six maintenance fields as a flat dict — fed
        directly into ``LocalSearchBackend.health().detail``."""
        return {
            "compactions": self.compactions,
            "last_compact_at_iso": self.last_compact_at_iso,
            "last_compact_error": self.last_compact_error,
            "emfile_recoveries": self.emfile_recoveries,
            "last_emfile_at_iso": self.last_emfile_at_iso,
            "last_recovery_error": self.last_recovery_error,
        }

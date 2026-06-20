"""ReembedService — the searchbase ``reembed`` admin operation.

Recomputes ALL vectors across the v4 collections and overwrites the
vector index in place. The single HTTP admin operation searchbase
exposes (``POST /v4/searchbase/reembed``); see
``docs/api/v4/searchbase.md``. Triggered only when ``embedding.dim``
changes (setup → server), so it is rare, blocking, and not resumable —
a re-run restarts from scratch.

What it touches: the ``vector`` column of every row in each v4
collection (``cards`` issue, ``positions`` claim, plus the kept
``insights`` / ``rounds``). The embed anchor is the ``text`` column the
backend already stores alongside each vector (written at upsert time
from ``cards.issue`` / ``positions.claim`` / insight body / round
turn), so there is no canonical re-read here — the immutable anchor
lives in the index. It does NOT touch canonical files, counters or
events.jsonl.

Concurrency: a module-level in-progress guard (one reembed at a time per
process) plus a live progress counter exposed via ``GET /v4/status``
(status flips to ``reembedding`` with a processed-so-far count while a
run is active).
"""
from __future__ import annotations

import time

from memorytalk.searchbase import SearchBackend
from memorytalk.service.searchbase_schema import (
    INSIGHTS, ROUNDS, V4_CARDS, V4_POSITIONS,
)

# Collections whose vectors a reembed rebuilds, in a stable order.
# ``cards`` first so the issue-collision NN path (the hot one) recovers
# soonest if a run is interrupted.
REEMBED_COLLECTIONS = (V4_CARDS, V4_POSITIONS, INSIGHTS, ROUNDS)


class ReembedError(Exception):
    """Base for reembed failures (mapped to HTTP by the router)."""


class ReembedDimMismatch(ReembedError):
    """400 — ``expected_dim`` != the server's reloaded settings dim."""


class ReembedInProgress(ReembedError):
    """409 — a reembed is already running in this process."""


class ReembedProviderDown(ReembedError):
    """500 — the embedding provider went wholly unavailable mid-run.
    Carries the processed-so-far count for the response body."""

    def __init__(self, processed: int):
        super().__init__("embedding provider unavailable during reembed")
        self.processed = processed


class ReembedService:
    """One per app. Owns the in-progress guard + the live progress state.

    ``config`` is reloaded (fresh settings off disk) at the start of each
    run so the dim safety check sees what setup just wrote, not a value
    cached at boot."""

    def __init__(self, config, search: SearchBackend | None):
        self.config = config
        self.search = search
        # In-progress guard + live progress, read by GET /v4/status.
        self._running = False
        self._processed = 0

    # ─── status surface (read by GET /v4/status) ───

    @property
    def running(self) -> bool:
        return self._running

    @property
    def processed(self) -> int:
        """Rows re-embedded so far in the active run (0 when idle)."""
        return self._processed

    # ─── helpers ───

    def _current_dim(self) -> int:
        """The server's CURRENT embedding dim — reloaded fresh off disk so
        a setup dim change made after boot is visible (the cached
        ``config.settings`` would otherwise still hold the boot-time dim)."""
        self.config._settings = None  # force a re-read on next access
        return int(self.config.settings.embedding.dim)

    async def _vector_index_dim(self) -> int | None:
        """The actual on-disk indexed dim (probe the cards collection — all
        v4 collections share the configured dim, so one probe is enough)."""
        if self.search is None:
            return None
        for coll in REEMBED_COLLECTIONS:
            d = await self.search.vector_index_dim(coll)
            if d is not None:
                return d
        return None

    async def _total_objects(self) -> int:
        if self.search is None:
            return 0
        total = 0
        for coll in REEMBED_COLLECTIONS:
            total += await self.search.count(coll)
        return total

    # ─── the operation ───

    async def reembed(self, expected_dim: int, dry_run: bool = False) -> dict:
        current_dim = self._current_dim()
        if expected_dim != current_dim:
            raise ReembedDimMismatch(
                f"dim mismatch: expected {expected_dim}, settings has {current_dim}"
            )

        if dry_run:
            return {
                "status": "dry_run",
                "cards_total": await self._total_objects(),
                "expected_dim": expected_dim,
                "current_dim": current_dim,
                "vector_index_dim": await self._vector_index_dim(),
            }

        if self._running:
            raise ReembedInProgress("reembed already in progress")
        self._running = True
        self._processed = 0
        processed = 0
        failed = 0
        t0 = time.monotonic()
        try:
            for coll in REEMBED_COLLECTIONS:
                if self.search is None:
                    break

                def _bump(n: int, _base: int = processed) -> None:
                    # n is per-collection progress; surface the global tally.
                    self._processed = _base + n

                p, f = await self.search.rebuild_collection(coll, on_progress=_bump)
                processed += p
                failed += f
                self._processed = processed
        except ConnectionError as e:
            # Provider went wholly unavailable mid-run — abort, 500 with the
            # processed-so-far count. No resume; a re-run starts over.
            raise ReembedProviderDown(processed) from e
        finally:
            self._running = False

        return {
            "status": "ok",
            "cards_processed": processed,
            "cards_failed": failed,
            "duration_seconds": round(time.monotonic() - t0, 3),
        }

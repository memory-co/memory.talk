"""IndexWriteBuffer — decouple LanceDB inserts from embedding batches.

Why this exists (issue #4 §4.3):

  The embedder side has to batch *small* because remote endpoints cap
  per-request input (e.g. DashScope's 10-row cap). The original
  ``IngestService._index_vectors`` mirrored that batch size into
  LanceDB writes — each embedder batch became one ``table.add()``
  call, and **each ``table.add()`` produces one new fragment + one new
  dataset version**. Over thousands of rounds this creates tens of
  thousands of tiny fragments; vector search (no ANN index) flat-scans
  every fragment, blowing the process fd ceiling (EMFILE).

  The two batch sizes have *nothing in common* — embedding is bound
  by remote API limits, LanceDB writes are bound by local IO. This
  module gives them their own batch budgets:

      embedder.embed(...)           # small (API cap)
        → buffer.add_rounds(...)    # accumulates
        → buffer.flush()            # large (settings.index.lance_flush_rows)
          → vectors.add_rounds(BIG_BATCH)
          → bump_indexed_count(...) per session

  Flush triggers (any one):
    1. Pending rows >= ``flush_rows`` threshold (size-based)
    2. ``flush_interval_seconds`` elapsed since last flush (time-based)
    3. Explicit ``flush()`` call (used by backfill at end-of-session +
       lifespan shutdown)

  ``bump_indexed_count`` moves from "embedding succeeded" to "row
  actually landed in LanceDB" — keeping ``sessions.indexed_round_count``
  in sync with what search can actually return. If a flush fails the
  pending rows are dropped + the session stays degraded (round_count >
  indexed_round_count), and the existing IndexBackfill loop catches up
  on the next pass. This deliberate "lossy on flush failure" choice
  avoids unbounded queue growth against a persistently failing endpoint.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import time
from collections import defaultdict
from typing import Iterable


_log = logging.getLogger("memorytalk.index_buffer")


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class IndexWriteBuffer:
    def __init__(
        self,
        vectors,           # LanceStore | None
        db,                # SQLiteStore
        flush_rows: int = 500,
        flush_interval_seconds: float = 30.0,
    ):
        self.vectors = vectors
        self.db = db
        self.flush_rows = max(1, int(flush_rows))
        self.flush_interval_seconds = max(0.0, float(flush_interval_seconds))

        # Pending rounds queued for the LanceDB rounds table. Kept as a
        # flat list (not per-session) because ``table.add`` is happiest
        # with one large heterogeneous batch — fragment count is per
        # call, not per session.
        self._pending_rows: list[dict] = []
        # Per-sid pending row count, replayed into ``bump_indexed_count``
        # on flush. Using defaultdict(int) so callers don't have to
        # check existence.
        self._pending_by_sid: dict[str, int] = defaultdict(int)

        # Serializes flush() against concurrent add_rounds() so the
        # snapshot we take and zero out is the snapshot we write.
        self._lock = asyncio.Lock()

        # Background time-based flusher.
        self._flusher_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

        # Observability — read by /v3/sync/status.
        self.last_flush_at_iso: str | None = None
        self.last_flush_error: str | None = None
        self.last_flush_rows: int = 0
        self.flush_count: int = 0

    # ─── public surface ──────────────────────────────────────────────

    @property
    def pending_rows(self) -> int:
        """Snapshot count (not lock-protected — observability only)."""
        return len(self._pending_rows)

    async def add_rounds(self, sid: str, rows: list[dict]) -> None:
        """Queue rows for the rounds table; flush synchronously if the
        threshold is hit. Called by IngestService + IndexBackfill in
        place of ``vectors.add_rounds``.

        No-op when the store has no vectors backend — the caller
        handles a disabled-vectors environment in its own branch."""
        if self.vectors is None or not rows:
            return
        async with self._lock:
            self._pending_rows.extend(rows)
            self._pending_by_sid[sid] += len(rows)
            ready = len(self._pending_rows) >= self.flush_rows
        if ready:
            await self.flush()

    async def flush(self) -> int:
        """Drain the buffer into LanceDB + bump per-session counters.

        Returns the number of rows flushed (0 if buffer was empty).
        On LanceDB write failure: the rows are *dropped*, the error
        is recorded, and the affected sessions stay degraded — the
        IndexBackfill loop is the recovery path. We don't re-queue
        because that would let a persistently failing embedder /
        lance build an unbounded in-memory queue."""
        if self.vectors is None:
            return 0
        async with self._lock:
            rows = self._pending_rows
            by_sid = dict(self._pending_by_sid)
            self._pending_rows = []
            self._pending_by_sid = defaultdict(int)
        if not rows:
            return 0
        try:
            await self.vectors.add_rounds(rows)
            now = _utc_iso()
            for sid, n in by_sid.items():
                if n > 0:
                    await self.db.sessions.bump_indexed_count(sid, n, now)
            self.last_flush_at_iso = now
            self.last_flush_error = None
            self.last_flush_rows = len(rows)
            self.flush_count += 1
            _log.debug("flushed %d rows across %d sessions", len(rows), len(by_sid))
            return len(rows)
        except Exception as e:
            _log.exception("flush failed rows=%d sessions=%d", len(rows), len(by_sid))
            self.last_flush_error = str(e)
            for sid in by_sid:
                try:
                    await self.db.sessions.set_last_index_error(
                        sid, f"flush failed: {e}", _utc_iso(),
                    )
                except Exception:
                    pass  # observability path; don't mask the flush error
            return 0

    # ─── lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the background time-based flusher. Idempotent.
        Skipped when ``flush_interval_seconds`` is 0 (tests use that
        to disable the background tick and rely on add-triggered or
        explicit flushes only)."""
        if self.flush_interval_seconds <= 0:
            return
        if self._flusher_task is not None and not self._flusher_task.done():
            return
        self._stop_event = asyncio.Event()
        self._flusher_task = asyncio.create_task(
            self._flusher_loop(), name="memorytalk.index_buffer.flusher",
        )

    async def stop(self) -> None:
        """Cancel the background flusher + best-effort final flush."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._flusher_task is not None:
            self._flusher_task.cancel()
            try:
                await self._flusher_task
            except (asyncio.CancelledError, Exception):
                pass
            self._flusher_task = None
        try:
            await self.flush()
        except Exception:
            _log.exception("shutdown flush failed")

    async def _flusher_loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.flush_interval_seconds,
                )
                # Stop was signaled — exit; stop() does the final flush.
                return
            except asyncio.TimeoutError:
                pass
            try:
                await self.flush()
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("background flush iteration failed")

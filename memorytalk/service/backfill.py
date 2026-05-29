"""Background backfill of missing LanceDB rounds.

Why this exists: ingest writes ``rounds.jsonl`` + the ``sessions`` row
synchronously, but the LanceDB vector index is fire-and-forget. If the
embedder fails on a batch (most commonly DashScope's 10-row cap on
``input``) we lose those rounds from search — jsonl/SQLite still have
the truth, but a search would silently return nothing for that text.

The backfill loop closes that gap. Each server start it scans the
``sessions`` table for ``indexed_round_count < round_count``, then for
each degraded session:

  1. Truncates the session's rows in LanceDB and resets
     ``indexed_round_count`` to 0 (handles the partial-success case
     where chunks 1 + 3 indexed but chunk 2 failed — without truncating,
     the next pass might leave a gap).
  2. Re-reads ``rounds.jsonl`` and re-embeds in batches of
     ``embedder.batch_size``.
  3. Commits ``indexed_round_count`` after each successful batch — so a
     crash mid-loop leaves a recoverable state (next start picks up
     where it left off).

On batch failure the session stays degraded and we move on; the loop
retries every ``poll_interval_seconds`` so transient failures (rate
limit, brief network blip) self-heal without operator action.

State surface for ``GET /v3/sync/status``: ``IndexBackfill.status``
exposes ``"running" | "idle" | "disabled"``, ``.last_error`` carries
the most recent batch failure.
"""
from __future__ import annotations
import asyncio
import datetime as _dt
import logging
import time
from typing import Literal

from memorytalk.provider.embedding import Embedder
from memorytalk.provider.lancedb import LanceStore, _segment
from memorytalk.repository import SQLiteStore
from memorytalk.service.sessions import _embed_input


_log = logging.getLogger("memorytalk.backfill")

# Process at most this many degraded sessions per poll. Bounds the
# memory + time cost of a single iteration; the loop comes back around
# on the next ``poll_interval_seconds`` for the rest. 10 keeps the
# total tail latency reasonable even with a slow remote embedder
# (10 sessions × ~6s each = 1 min per pass).
_BATCH_OF_SESSIONS = 10

# How often to recheck for new degradation after the queue drained.
# 60s is a sweet spot: short enough that newly-failing ingests get
# repaired quickly, long enough that an idle server doesn't burn CPU.
_POLL_INTERVAL_SECONDS = 60.0

# Backoff after a session-level failure so a flapping endpoint doesn't
# spin the loop. Applies between attempts on the *same* session within
# a single pass — different sessions still get tried in sequence.
_PER_SESSION_RETRY_SLEEP = 2.0

# How often the background loop runs LanceDB compaction. The append-only
# ingest path leaks one fragment per embedder batch; compaction merges
# them back down so vector search (which flat-scans fragments) doesn't
# accumulate enough open files to hit EMFILE. 30 min trades a little
# periodic IO for bounded fragment growth between passes.
_COMPACT_INTERVAL_SECONDS = 1800.0


class IndexBackfill:
    """Owns the backfill loop + exposes status for ``/v3/sync/status``."""

    def __init__(
        self,
        db: SQLiteStore,
        vectors: LanceStore | None,
        embedder: Embedder | None,
        poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
        compact_interval_seconds: float = _COMPACT_INTERVAL_SECONDS,
        index_buffer=None,  # IndexWriteBuffer | None
    ):
        self.db = db
        self.vectors = vectors
        self.embedder = embedder
        self.poll_interval_seconds = poll_interval_seconds
        self.compact_interval_seconds = compact_interval_seconds
        # When provided, all LanceDB writes go through the buffer so
        # backfill respects the same fragment-count discipline as ingest.
        # _reindex_session forces a flush at end-of-session so per-
        # session indexed counters land before the next session starts.
        self.index_buffer = index_buffer
        # Externally-visible state (read by ``api/sync.py``).
        self.status: Literal["running", "idle", "disabled"] = (
            "disabled" if (vectors is None or embedder is None) else "idle"
        )
        self.last_error: str | None = None
        self._task: asyncio.Task | None = None
        # Compaction runs on its own cadence, independent of the
        # re-embed loop. Seed ``_last_compact_at`` to *now* so the
        # periodic timer doesn't immediately fire on top of the
        # startup one-shot (``trigger_startup_compaction``) — the first
        # periodic compaction lands one full interval after boot.
        self._compact_task: asyncio.Task | None = None
        self._last_compact_at: float = time.monotonic()
        # ISO-time + dedicated error field for /v3/sync/status lance
        # health (separate from self.last_error which mixes re-embed
        # failures and compaction failures).
        self.last_compact_at_iso: str | None = None
        self.last_compact_error: str | None = None

    # ─── lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the loop as a background task. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        if self.vectors is None or self.embedder is None:
            # No vectors / no embedder → nothing to backfill into.
            self.status = "disabled"
            return
        self._task = asyncio.create_task(self._loop(), name="memorytalk.backfill")

    def trigger_startup_compaction(self) -> None:
        """Fire a one-shot compaction in the background at boot.

        Deliberately a *side path* off the re-embed loop: it's gated
        only on ``vectors`` (not ``embedder``), so even an
        embedder-less boot still compacts leftover fragments from a
        prior run. This is the "restart always re-runs compaction"
        guarantee — a degenerate fragment pile gets ground down on
        every server start without operator action.
        """
        if self.vectors is None:
            return
        if self._compact_task is not None and not self._compact_task.done():
            return
        self._compact_task = asyncio.create_task(
            self._compact_once(), name="memorytalk.compact.startup",
        )

    async def stop(self) -> None:
        for task in (self._task, self._compact_task):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        self._compact_task = None
        self.status = "idle"

    # ─── compaction ──────────────────────────────────────────────────

    async def _compact_once(self) -> None:
        """Compact both LanceDB tables. Swallows errors (best-effort
        maintenance — a compaction failure must never take the server
        down or block re-embedding). Records the attempt time so the
        periodic timer paces off it."""
        self._last_compact_at = time.monotonic()
        self.last_compact_at_iso = _utc_iso()
        if self.vectors is None:
            return
        compact_error: str | None = None
        for table_name in (self.vectors.ROUNDS, self.vectors.CARDS):
            try:
                result = await self.vectors.optimize(table_name)
                _log.info("compaction done %s", result)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # EMFILE here is possible on a first run against a
                # badly-fragmented table (compaction itself opens
                # files). Log + move on; the next start retries and
                # each partial merge makes the next attempt lighter.
                _log.exception("compaction failed table=%s", table_name)
                compact_error = f"compact {table_name}: {e}"
                self.last_error = compact_error
        # Clear on full success so the status field reflects current
        # state, not the last historical failure.
        self.last_compact_error = compact_error

    # ─── loop ────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while True:
            # Periodic compaction rides the same loop — checked every
            # iteration but gated on its own interval so it runs at most
            # once per ``compact_interval_seconds`` regardless of how
            # often the degraded-poll wakes up.
            if (time.monotonic() - self._last_compact_at
                    >= self.compact_interval_seconds):
                await self._compact_once()

            try:
                degraded = await self.db.sessions.list_degraded(
                    limit=_BATCH_OF_SESSIONS
                )
            except Exception as e:
                _log.exception("backfill: list_degraded failed")
                self.last_error = f"list_degraded: {e}"
                await asyncio.sleep(self.poll_interval_seconds)
                continue

            if not degraded:
                self.status = "idle"
                await asyncio.sleep(self.poll_interval_seconds)
                continue

            self.status = "running"
            for s in degraded:
                try:
                    await self._reindex_session(s)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    # Per-session failure stays local — keep going.
                    _log.exception(
                        "backfill: reindex failed sid=%s", s["session_id"],
                    )
                    self.last_error = f"{s['session_id']}: {e}"
                    await self.db.sessions.set_last_index_error(
                        s["session_id"], str(e), _utc_iso(),
                    )
                    await asyncio.sleep(_PER_SESSION_RETRY_SLEEP)

    # ─── per-session work ────────────────────────────────────────────

    async def _reindex_session(self, s: dict) -> None:
        """Truncate + re-embed all rounds for one degraded session.

        Truncate-and-rewrite (vs. incremental "embed only the missing
        idxs") because partial-success states can leave non-contiguous
        gaps in LanceDB that ``indexed_round_count`` doesn't fully
        describe — only the count, not the set. Re-embedding everything
        guarantees the LanceDB rounds for this session exactly match
        ``rounds.jsonl``. Wasted work in the happy path is bounded by
        ``round_count`` per degraded session, which is fine for a
        background task.
        """
        sid = s["session_id"]
        source = s["source"]
        target = int(s["round_count"] or 0)
        if target == 0:
            return

        # 1. Read truth from jsonl. The storage layer turns "file
        # missing" into an empty read (vs raising FileNotFoundError),
        # so we detect corruption by comparing against the SQLite
        # round_count — if the jsonl is short or empty but SQLite
        # expects N rounds, the install is inconsistent and we can't
        # reindex; mark with an explanatory error and skip so the user
        # can investigate without us looping forever on it.
        rounds = await self.db.sessions.read_rounds_file(source, sid)
        if not rounds:
            await self.db.sessions.set_last_index_error(
                sid,
                f"rounds.jsonl is missing or empty, but sessions row "
                f"expects round_count={target}",
                _utc_iso(),
            )
            return
        if len(rounds) < target:
            await self.db.sessions.set_last_index_error(
                sid,
                f"rounds.jsonl has {len(rounds)} rounds, sessions row "
                f"expects round_count={target} — proceeding with what's "
                f"on disk",
                _utc_iso(),
            )
            # Fall through and reindex whatever's actually on disk;
            # better than not indexing at all. ``indexed_round_count``
            # may not reach ``target`` which keeps the row in the
            # degraded set (visible to the user).

        # 2. Wipe LanceDB rows + reset counter together — the counter is
        # the source of truth for "how complete is the index". Doing
        # them in sequence (not transactional across two stores) means
        # a crash here leaves "0 in lance, 0 in counter" which is still
        # a valid degraded state that the next pass will retry.
        #
        # Drain the IndexWriteBuffer first when present — otherwise a
        # pending row for this sid from a concurrent ingest would be
        # written *after* our delete, leaving the index inconsistent
        # with sessions.indexed_round_count.
        if self.index_buffer is not None:
            try:
                await self.index_buffer.flush()
            except Exception:
                pass  # observability lives on the buffer itself
        await self.vectors.delete_session_rounds(sid)
        # Reset counter via bump with -current to land at 0.
        current_indexed = int(s["indexed_round_count"] or 0)
        if current_indexed > 0:
            await self.db.sessions.bump_indexed_count(
                sid, -current_indexed, _utc_iso(),
            )

        # 3. Chunked re-embed; bump counter per successful chunk so
        # interrupts leave a usable resume state.
        batch_size = getattr(self.embedder, "batch_size", 100)
        if not isinstance(batch_size, int) or batch_size < 1:
            batch_size = 100

        for i in range(0, len(rounds), batch_size):
            chunk = rounds[i:i + batch_size]
            texts = [_embed_input(r.get("text") or "") for r in chunk]
            vectors = await self.embedder.embed(texts)
            lance_rows = [
                {
                    "session_id": sid,
                    "idx": r["idx"],
                    "role": r.get("role") or "",
                    "text": _segment(r.get("text") or ""),
                    "vector": v,
                }
                for r, v in zip(chunk, vectors)
            ]
            if self.index_buffer is not None:
                await self.index_buffer.add_rounds(sid, lance_rows)
            else:
                await self.vectors.add_rounds(lance_rows)
                await self.db.sessions.bump_indexed_count(
                    sid, len(chunk), _utc_iso(),
                )

        # End-of-session flush — ensures this session's bump_indexed_count
        # lands before the loop moves to the next degraded row, so the
        # backfill snapshot in list_degraded() reflects reality.
        if self.index_buffer is not None:
            try:
                await self.index_buffer.flush()
            except Exception:
                pass

        # Clear last_error on full success.
        await self.db.sessions.bump_indexed_count(sid, 0, _utc_iso())


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

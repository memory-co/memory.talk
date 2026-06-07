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
from typing import Literal

from memorytalk.repository import SQLiteStore
from memorytalk.searchbase import Doc, SearchBackend
from memorytalk.service.searchbase_schema import ROUNDS, cap_text, round_doc_id


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


class IndexBackfill:
    """Owns the backfill loop + exposes status for ``/v3/sync/status``.

    Re-embed only — fragment compaction + EMFILE recovery now live inside
    the searchbase instance, not here.
    """

    def __init__(
        self,
        db: SQLiteStore,
        search: SearchBackend | None,
        poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
    ):
        self.db = db
        self.search = search
        self.poll_interval_seconds = poll_interval_seconds
        # Externally-visible state (read by ``api/sync.py``).
        self.status: Literal["running", "idle", "disabled"] = (
            "disabled" if search is None else "idle"
        )
        self.last_error: str | None = None
        self._task: asyncio.Task | None = None

    # ─── lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the loop as a background task. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        if self.search is None:
            # No searchbase → nothing to backfill into.
            self.status = "disabled"
            return
        self._task = asyncio.create_task(self._loop(), name="memorytalk.backfill")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        self.status = "idle"

    # ─── loop ────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while True:
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
        # searchbase upsert is immediate-durable, so the delete + reset +
        # re-upsert run in sequence with no buffer to drain.
        await self.search.delete_where(ROUNDS, {"session_id": sid})
        # Reset counter via bump with -current to land at 0.
        current_indexed = int(s["indexed_round_count"] or 0)
        if current_indexed > 0:
            await self.db.sessions.bump_indexed_count(
                sid, -current_indexed, _utc_iso(),
            )

        # 3. Re-embed everything on disk in one durable upsert (searchbase
        # owns embedding + batching), then bump the counter.
        docs = [
            Doc(
                id=round_doc_id(sid, r["idx"]),
                text=cap_text(r.get("text")),
                fields={
                    "session_id": sid,
                    "idx": r["idx"],
                    "role": r.get("role") or "",
                },
            )
            for r in rounds
        ]
        await self.search.upsert(ROUNDS, docs)
        await self.db.sessions.bump_indexed_count(sid, len(docs), _utc_iso())


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

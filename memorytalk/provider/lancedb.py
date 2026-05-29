"""Async LanceDB store for the v3 search backend.

Two tables, both indexed for FTS and vector queries:

- ``cards``  — one row per card.   ``{card_id, text, vector}``
- ``rounds`` — one row per round.  ``{session_id, idx, role, text, vector}``

This is the v3 search source of truth — search.md's per-round recall maps
directly onto rows of the ``rounds`` table, and the card-level ad slots
in search results come from the ``cards`` table. SQLite holds zero search
state; jsonl files hold zero search state.
"""
from __future__ import annotations
import asyncio
import datetime as _dt
import logging
from pathlib import Path
from typing import Optional

import pyarrow as pa


_log = logging.getLogger("memorytalk.lancedb")


def _is_emfile(exc: BaseException) -> bool:
    """Recognize Lance's wrapped EMFILE — comes through as a
    ``RuntimeError`` whose ``str()`` contains "Too many open files".
    We can't match on errno because Lance wraps the OS error inside
    its own ``LanceError(IO)`` before raising. String match is fragile
    but it's the only signal Lance gives us on this path."""
    msg = str(exc)
    return "Too many open files" in msg or "(os error 24)" in msg


def _segment(text: str) -> str:
    """jieba 预分词,空格连接(jieba.cut 同步,亚毫秒级)。"""
    import jieba
    return " ".join(jieba.cut(text or ""))


def _in_clause(ids: list[str], column: str) -> Optional[str]:
    if not ids:
        return None
    quoted = ", ".join("'" + i.replace("'", "''") + "'" for i in ids)
    return f"{column} IN ({quoted})"


class LanceStore:
    CARDS = "cards"
    ROUNDS = "rounds"

    def __init__(self, db, data_dir: Path, dim: int):
        self.db = db
        self.data_dir = data_dir
        self.dim = dim
        # Per-table "FTS index confirmed present" memo. Avoids a
        # ``list_indices()`` round trip on every search call once we've
        # verified the index exists. Invalidated only on process restart
        # (we don't drop FTS indices at runtime).
        self._fts_index_known: set[str] = set()
        # EMFILE recovery state — see _recover_from_emfile / _search_with_recovery.
        self._recovery_lock = asyncio.Lock()
        self.emfile_recoveries: int = 0
        self.last_emfile_at_iso: str | None = None
        self.last_recovery_error: str | None = None
        self._cards_schema = pa.schema([
            pa.field("card_id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ])
        # One row per round. ``idx`` is the session-internal index; pair
        # ``(session_id, idx)`` uniquely identifies a round.
        self._rounds_schema = pa.schema([
            pa.field("session_id", pa.string()),
            pa.field("idx", pa.int32()),
            pa.field("role", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ])

    @classmethod
    async def create(cls, data_dir: Path, dim: int = 384) -> "LanceStore":
        import lancedb
        db = await lancedb.connect_async(str(data_dir))
        return cls(db, Path(data_dir), dim)

    async def _exists(self, name: str) -> bool:
        result = await self.db.list_tables()
        return name in (result.tables if hasattr(result, "tables") else result)

    async def _get_or_create_cards(self):
        if await self._exists(self.CARDS):
            return await self.db.open_table(self.CARDS)
        return await self.db.create_table(self.CARDS, schema=self._cards_schema)

    async def _get_or_create_rounds(self):
        if await self._exists(self.ROUNDS):
            return await self.db.open_table(self.ROUNDS)
        return await self.db.create_table(self.ROUNDS, schema=self._rounds_schema)

    # ────────── cards ──────────

    async def add_card(self, card_id: str, text: str, embedding: list[float]) -> None:
        table = await self._get_or_create_cards()
        await table.delete(f"card_id = '{card_id}'")
        await table.add([{"card_id": card_id, "text": _segment(text), "vector": embedding}])

    async def delete_cards(self, card_ids: list[str]) -> None:
        if not await self._exists(self.CARDS) or not card_ids:
            return
        table = await self.db.open_table(self.CARDS)
        expr = " OR ".join(f"card_id = '{cid}'" for cid in card_ids)
        await table.delete(expr)

    # ────────── rounds ──────────

    async def add_rounds(self, rows: list[dict]) -> None:
        """Bulk insert per-round rows.

        Each row: ``{session_id, idx, role, text, vector}`` where ``text``
        is already segmented (caller's responsibility — typically via
        ``_segment``) and ``vector`` is a list[float] of length ``dim``.

        Idempotent on (session_id, idx): callers should ``delete_rounds``
        first if they want to replace existing rows. The default ingest
        path doesn't replace existing rounds (v3 is append-only), so this
        is just ``add``.
        """
        if not rows:
            return
        table = await self._get_or_create_rounds()
        await table.add(rows)

    async def delete_session_rounds(self, session_id: str) -> None:
        if not await self._exists(self.ROUNDS):
            return
        table = await self.db.open_table(self.ROUNDS)
        await table.delete(f"session_id = '{session_id}'")

    # ────────── compaction ──────────

    async def optimize(self, table_name: str) -> dict:
        """Compact small fragments + prune old dataset versions.

        Why this is load-bearing: the ingest / backfill path is
        append-only — every embedder batch is one ``table.add`` →
        one new fragment + one new dataset version (manifest + txn
        file). Left unchecked these accumulate without bound (tens of
        thousands of files in production). Search has **no vector ANN
        index** (the only index we build is FTS), so vector queries
        flat-scan every fragment, opening every fragment's files at
        once — past a few thousand fragments this blows the process
        file-descriptor ceiling (EMFILE / "Too many open files").

        ``optimize`` is LanceDB's VACUUM: merge fragments, fold new
        data into indices, and prune old versions. We pass
        ``cleanup_older_than=timedelta(0)`` so **every version except
        the latest is removed** — that's what actually reclaims the
        manifest/txn file explosion (plain compaction merges data but
        leaves the old versions' files around until pruned). Trade-off:
        dataset time-travel history is discarded; v3 doesn't use it.

        ``delete_unverified`` stays at its safe default (False) so a
        concurrent ingest / backfill write in flight can't be corrupted.

        No-op (returns ``skipped``) when the table doesn't exist yet.
        """
        import datetime as _dt

        if not await self._exists(table_name):
            return {"table": table_name, "skipped": "missing"}
        table = await self.db.open_table(table_name)
        stats = await table.optimize(cleanup_older_than=_dt.timedelta(0))
        # OptimizeStats shape drifts across lancedb versions; don't
        # hard-depend on field names — stringify for the caller's log.
        return {"table": table_name, "stats": str(stats)}

    # ────────── FTS index maintenance ──────────

    async def ensure_fts_index(self, table_name: str) -> None:
        """Create the FTS index on the ``text`` column if absent.

        Idempotent + memoized: once we've confirmed an FTS index covers
        ``text`` for a given table in this process, future calls are
        free. We don't drop indices at runtime, so the memo can't go
        stale within a single process lifetime — invalidation = restart.

        **Exception handling note (issue #4 §4.2 fix):** earlier this
        function swallowed any error from ``list_indices()`` and
        fell through to ``create_index(..., replace=True)``. Under
        EMFILE the swallowed list call was followed by a fresh index
        build, *adding* pressure exactly when the process was already
        over its fd quota. Now: a successful ``list_indices()`` that
        returns no ``text`` index is the only signal to create; any
        IO exception from ``list_indices()`` propagates so the upstream
        EMFILE recovery path can take over instead of compounding.
        """
        if table_name in self._fts_index_known:
            return
        if not await self._exists(table_name):
            return
        from lancedb.index import FTS
        table = await self.db.open_table(table_name)
        # Let list_indices' exceptions bubble — see docstring.
        indices = await table.list_indices()
        for idx in indices:
            cols = getattr(idx, "columns", None) or []
            if "text" in cols:
                self._fts_index_known.add(table_name)
                return
        # Confirmed absent — create. ``replace=False`` so a concurrent
        # creator can't race us into a double build; if that ever fires
        # the second caller gets a clear error rather than a silent
        # second-rebuild storm.
        await table.create_index(
            "text", config=FTS(base_tokenizer="whitespace", with_position=True),
            replace=False,
        )
        self._fts_index_known.add(table_name)

    # ────────── search ──────────

    async def search_cards(
        self,
        query: str,
        vector: list[float] | None,
        top_k: int,
        where: str | None = None,
    ) -> list[dict]:
        """Hybrid FTS+vector search on the cards table.

        Returns a list of ``{card_id, _score}`` rows (LanceDB also returns
        text/vector but callers usually just need card_id + relevance).
        Empty query → vector-only; no query and no vector → empty result.
        """
        return await self._search_with_recovery(
            self.CARDS, query, vector, top_k, where,
        )

    async def search_rounds(
        self,
        query: str,
        vector: list[float] | None,
        top_k: int,
        where: str | None = None,
    ) -> list[dict]:
        """Hybrid FTS+vector search on the rounds table.

        Returns ``{session_id, idx, role, text, _score}`` rows. Caller is
        responsible for aggregating per session, dereffing the text from
        jsonl for display, etc.
        """
        return await self._search_with_recovery(
            self.ROUNDS, query, vector, top_k, where,
        )

    # ────────── EMFILE recovery (issue #4 §6.2 fix) ──────────

    async def _search_with_recovery(
        self, table_name: str, query: str,
        vector: list[float] | None, top_k: int, where: str | None,
    ) -> list[dict]:
        """Run a hybrid search; on EMFILE, drive a recovery once + retry.

        Recovery (compaction + connection reset) is necessary because:
        - compaction reclaims fragments on disk → fewer files to open;
        - the in-process LanceDB readers hold fds to files Compaction
          unlinked → only a fresh ``connect_async`` releases those.

        Retry is gated to exactly one attempt: if the post-recovery
        query still EMFILEs the underlying fragment / fd-budget mismatch
        is past what we can fix in-process, and the original error
        propagates as a 500 — operator action (restart, raise ulimit)
        is required.
        """
        if not await self._exists(table_name):
            return []
        try:
            table = await self.db.open_table(table_name)
            return await _run_hybrid(table, query, vector, top_k, where)
        except Exception as e:
            if not _is_emfile(e):
                raise
            _log.warning(
                "EMFILE on search table=%s; triggering recovery", table_name,
            )
            await self._recover_from_emfile()
            # Single retry — see docstring.
            if not await self._exists(table_name):
                return []
            table = await self.db.open_table(table_name)
            return await _run_hybrid(table, query, vector, top_k, where)

    async def _recover_from_emfile(self) -> None:
        """Compact both tables + reset the LanceDB connection.

        Lock-protected so concurrent EMFILE-ing requests don't pile up
        N recoveries. The first request through the lock does the work;
        followers see ``emfile_recoveries`` advanced and skip — they
        proceed straight to retry, which now sees a fresh connection.
        """
        gen_before = self.emfile_recoveries
        async with self._recovery_lock:
            if self.emfile_recoveries > gen_before:
                return  # someone else recovered while we waited
            # 1. Compact — best-effort; failure here doesn't block retry.
            for table_name in (self.ROUNDS, self.CARDS):
                try:
                    await self.optimize(table_name)
                except Exception as e:
                    _log.exception(
                        "optimize during EMFILE recovery failed table=%s",
                        table_name,
                    )
                    self.last_recovery_error = (
                        f"optimize {table_name}: {e}"
                    )
            # 2. Reset connection — closes the held fds. Without this,
            # post-compaction the process is still pinned to old files.
            try:
                import lancedb
                try:
                    await self.db.close()
                except Exception:
                    pass  # already closed / unsupported — best effort
                self.db = await lancedb.connect_async(str(self.data_dir))
            except Exception as e:
                _log.exception("connection reset during EMFILE recovery failed")
                self.last_recovery_error = f"reconnect: {e}"
                raise
            self.emfile_recoveries += 1
            self.last_emfile_at_iso = _dt.datetime.now(_dt.UTC).isoformat(
                timespec="seconds",
            ).replace("+00:00", "Z")


async def _run_hybrid(
    table, query: str, vector: list[float] | None,
    top_k: int, where: str | None,
) -> list[dict]:
    """Internal: hybrid FTS + vector with RRF reranking.

    Reranker history (read before changing — there's a trap here):

    - **RRFReranker(K=60)** (current). Rank-based fusion. Output scale
      is small (~0.033 top) and the rank-1-vs-rank-2 differential is
      tiny (~0.0003), so the absolute score doesn't reflect match
      strength. We compensate downstream:
        * ``service/search.py:_aggregate_session_relevance`` is ``max``
          (not noisy-OR — see its docstring for why noisy-OR was wrong);
        * ``ranking_formula`` only consumes RRF as one signal among
          stats / age.

    - **LinearCombinationReranker (tried 2026-05-23, reverted same day)**.
      Looked attractive because it nominally uses actual BM25 + vector
      scores. But in ``lancedb==0.30.x`` the implementation is
      **inverted and unnormalized**:
      ``combined = 1 - (0.7 * vec_sim + 0.3 * bm25_raw)`` where BM25
      is unbounded (~30+ for strong matches) and vec_sim is [0, 1].
      Higher BM25 → lower combined → after min-max normalization the
      perfect-match round lands near 0 and noisy "fill" rows land
      near 1. A perfect-text-match round vanished from top 1000 in
      production — see ``docs/report/2026-05-23-search-linear-combination-regression.md``
      for the evidence chain. Lance's
      own docstring carries a ``TODO: pretty confusing as we invert
      scores``.

    **Do not switch to LinearCombinationReranker without** (a) Lance
    upstream fixing the inversion + adding normalization, or (b)
    landing a search-quality regression test that asserts perfect
    text matches stay in top-k on a fixed corpus.
    """
    from lancedb.rerankers import RRFReranker

    q = table.query()
    has_vector = vector is not None and len(vector) > 0
    has_text = bool(query and query.strip())

    if has_vector:
        q = q.nearest_to(vector)
    if has_text:
        q = q.nearest_to_text(_segment(query))
    if not has_vector and not has_text:
        # Pure scan — no relevance to compute, only useful when a `where`
        # filter narrows things. The reranker would crash without anchors.
        if where:
            q = q.where(where)
        q = q.limit(top_k)
        rows = await q.to_list()
        for r in rows:
            r["_score"] = 0.0
        return rows
    if has_vector and has_text:
        q = q.rerank(reranker=RRFReranker(K=60))
    if where:
        q = q.where(where)
    q = q.limit(top_k)
    rows = await q.to_list()
    # Normalize the score field: LanceDB returns it under different names
    # depending on mode (_distance / _relevance_score / _score). Project
    # to a single ``_score`` so the caller doesn't care.
    for r in rows:
        if "_score" in r:
            continue
        if "_relevance_score" in r:
            r["_score"] = float(r["_relevance_score"])
        elif "_distance" in r:
            # cosine distance in [0,2] → similarity in [-1,1]; map to [0,1].
            r["_score"] = max(0.0, 1.0 - float(r["_distance"]) / 2.0)
        else:
            r["_score"] = 0.0
    return rows

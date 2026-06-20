"""LocalSearchBackend — embedding + CollectionIndex behind the port.

Owns the embedder, the generic CollectionIndex, and a Maintenance
subsystem (compaction loop + EMFILE recovery + observability). Maps
generic Docs onto generic ``{id, text, vector, **fields}`` rows. There
is deliberately NO card / round / session vocabulary here —
``collection`` is an opaque string and every collection flows through
the same code path.

Self-management is delegated to :class:`Maintenance` (one file owns it)
rather than spread across this module's ``_maintenance_loop`` and
``CollectionIndex``'s recovery methods.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from memorytalk.searchbase._types import (
    AdminBackend, Doc, Hit, IndexHealth, Query, SearchError,
)
from memorytalk.searchbase.local._admin import LocalAdminBackend
from memorytalk.searchbase.local._logging import setup_file_logging
from memorytalk.searchbase.local.index import CollectionIndex
from memorytalk.searchbase.local.maintenance import Maintenance
from memorytalk.searchbase.local.util import (
    NON_DOC_FIELDS, split_text, where_from_match,
)


# Loggers per category — these write to dedicated files when log_dir
# is configured at create-time. See searchbase/local/_logging.py.
_qlog = logging.getLogger("memorytalk.searchbase.query")
_ilog = logging.getLogger("memorytalk.searchbase.index")


# How often the maintenance coroutine compacts fragments. 30 min trades
# a little periodic IO for bounded fragment growth between restarts.
_COMPACT_INTERVAL_SECONDS = 1800.0


def _cosine(a, b) -> float:
    """Cosine similarity clamped to [0, 1], robust to un-normalized vectors
    and a zero vector (→ 0.0). Negative cosines (rare for text embeddings,
    where unrelated ≈ 0) clamp to 0 so "unrelated" reads as a clean miss.
    Used by ``nearest`` so its score is a real, thresholdable similarity
    regardless of the table's distance metric."""
    import numpy as np

    va = np.asarray(a, dtype="float64")
    vb = np.asarray(b, dtype="float64")
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    cos = float(np.dot(va, vb) / (na * nb))
    return max(0.0, min(1.0, cos))


class LocalSearchBackend:
    def __init__(self, index: CollectionIndex, embedder, max_text_length: int,
                 auto_split: set[str], compact_interval_seconds: float):
        self._embedder = embedder
        self._index: CollectionIndex | None = index
        self._max_text_length = max_text_length
        self._auto_split = auto_split
        self._compact_interval_seconds = compact_interval_seconds
        # Wired in ``create``. ``None`` only during the brief window
        # between __init__ and create's setup, or after ``close``.
        self._maintenance: Maintenance | None = None

    @classmethod
    async def create(
        cls, *, data_dir, dim: int, embedder,
        collections: dict[str, dict], max_text_length: int = 100_000,
        compact_interval_seconds: float = _COMPACT_INTERVAL_SECONDS,
        log_dir: Path | str | None = None,
        name: str = "",
    ) -> "LocalSearchBackend":
        """Open a backend with a declared schema.

        ``name`` defaults to empty — data lands directly under
        ``data_dir/`` (matches the 0.8.x flat layout, so a 0.8.x install
        can be migrated in place by the ``memorytalk.migration`` runner
        without moving files around). A non-empty name maps to
        ``data_dir/<name>/``, which used to be the instance-versioning
        story; left in as an escape hatch but no longer the default.

        The returned instance is already running — Maintenance starts
        here, so periodic compaction + EMFILE recovery are live before
        the first caller. Schema evolution (renames, added columns)
        happens through the separate ``migration`` framework, not via
        construction parameters.

        ``log_dir`` (optional): if provided, searchbase writes
        per-category log files under it (``maintenance.log`` /
        ``query.log`` / ``index.log``) — see
        ``searchbase/local/_logging.py``."""
        if log_dir is not None:
            setup_file_logging(log_dir)
        # ``Path("/foo") / "" == Path("/foo")`` so empty-name is the
        # flat layout.
        backend_dir = Path(data_dir) / name if name else Path(data_dir)
        index = await CollectionIndex.create(
            backend_dir, dim=dim, collections=collections,
        )
        auto_split = {
            n for n, spec in collections.items() if spec.get("auto_split")
        }
        self = cls(
            index, embedder, max_text_length, auto_split,
            compact_interval_seconds,
        )
        # Wire maintenance: one subsystem owns the compaction loop, the
        # EMFILE recovery, and all the observability counters.
        # ``index.attach_maintenance`` lets the search hot path delegate
        # EMFILEs back through the Maintenance singleton without owning
        # any of the policy.
        self._maintenance = Maintenance(
            index, compact_interval_seconds=compact_interval_seconds,
        )
        index.attach_maintenance(self._maintenance)
        await self._maintenance.start()
        return self

    # ─── lifecycle ───

    async def close(self) -> None:
        if self._maintenance is not None:
            await self._maintenance.stop()
            self._maintenance = None
        self._index = None

    @property
    def ready(self) -> bool:
        return self._index is not None

    async def health(self) -> IndexHealth:
        """Surface Maintenance's six-field health dict directly. We
        don't add or rearrange anything here — the Maintenance class
        is the single source of truth for what self-maintenance
        reports."""
        detail: dict = (
            self._maintenance.health() if self._maintenance is not None else {}
        )
        return IndexHealth(ready=self.ready, detail=detail)

    def admin(self) -> AdminBackend:
        """Return the low-level admin port. Used by the migration
        framework only; business service code never touches this."""
        if self._index is None:
            raise RuntimeError("backend is closed; cannot return admin")
        return LocalAdminBackend(self._index)

    # ─── write ───

    async def upsert(self, collection: str, docs: list[Doc]) -> None:
        if self._index is None or not docs:
            return
        if collection in self._auto_split:
            rows = await self._split_rows(docs)
        else:
            rows = await self._plain_rows(docs)
        await self._index.upsert(collection, rows)
        _ilog.info(
            "upsert coll=%s docs=%d rows=%d",
            collection, len(docs), len(rows),
        )

    async def _plain_rows(self, docs: list[Doc]) -> list[dict]:
        """One row per doc; over-length is rejected (no silent loss)."""
        for d in docs:
            if len(d.text) > self._max_text_length:
                raise SearchError(
                    f"doc {d.id!r} text length {len(d.text)} exceeds "
                    f"max_text_length {self._max_text_length}"
                )
        vecs = await self._embedder.embed([d.text for d in docs])
        return [
            {"id": d.id, "text": d.text, "vector": v, **(d.fields or {})}
            for d, v in zip(docs, vecs)
        ]

    async def _split_rows(self, docs: list[Doc]) -> list[dict]:
        """Split each over-length doc into ``_chunk`` rows that share a
        ``_base_id`` (= the logical doc id). The chunking is invisible on
        read — the index collapses it back. ``id`` = ``f"{base}#{i}"``."""
        plan: list[tuple[Doc, int, str]] = []
        for d in docs:
            for i, chunk in enumerate(split_text(d.text, self._max_text_length)):
                plan.append((d, i, chunk))
        vecs = await self._embedder.embed([chunk for _, _, chunk in plan])
        return [
            {
                "id": f"{d.id}#{i}", "_base_id": d.id, "_chunk": i,
                "text": chunk, "vector": v, **(d.fields or {}),
            }
            for (d, i, chunk), v in zip(plan, vecs)
        ]

    async def delete(self, collection: str, ids: list[str]) -> None:
        if self._index is None:
            return
        await self._index.delete(collection, ids)
        _ilog.info("delete coll=%s ids=%d", collection, len(ids))

    async def delete_where(self, collection: str, match: dict) -> None:
        if self._index is None:
            return
        await self._index.delete_where(collection, where_from_match(match))
        _ilog.info(
            "delete_where coll=%s match=%s",
            collection, ",".join(sorted(match)) if match else "",
        )

    async def count(self, collection: str, match: dict | None = None) -> int:
        if self._index is None:
            return 0
        return await self._index.count(collection, where_from_match(match))

    # ─── reembed (admin: rebuild all vectors of a collection) ───

    async def vector_index_dim(self, collection: str) -> int | None:
        """Dim the collection's vector column is actually indexed at on
        disk (may differ from the configured dim when the embedding dim
        changed but no reembed has run). ``None`` if absent/closed."""
        if self._index is None:
            return None
        return await self._index.vector_index_dim(collection)

    async def rebuild_collection(
        self, collection: str, *, on_progress=None,
    ) -> tuple[int, int]:
        """Re-embed every stored row's anchor ``text`` and OVERWRITE its
        vector in place. The embed anchor is the ``text`` column written at
        upsert time (``cards.issue`` / ``positions.claim`` / insight body /
        round turn) — so no canonical re-read is needed; the index already
        holds the immutable anchor alongside each vector.

        Semantics (mirrors the reembed contract):
          * one embed call per row → a single row's embed failure is
            isolated: it's counted as failed and the (stale) vector is left
            untouched, the run continues;
          * if the provider raises ``ConnectionError`` the run aborts
            (re-raised) so the caller can return 500 with the
            processed-so-far count — a wholly-unavailable provider must not
            be swallowed as N per-row failures;
          * ``on_progress(processed)`` is invoked after each successful row
            so the service can expose a live counter via ``GET /v4/status``.

        Returns ``(processed, failed)``. Does NOT touch canonical files,
        counters or events — pure vector overwrite.
        """
        if self._index is None:
            return (0, 0)
        rows = await self._index.scan_all(collection)
        processed = 0
        failed = 0
        for r in rows:
            text = r.get("text") or ""
            try:
                vec = await self._embedder.embed_one(text)
            except ConnectionError:
                # Provider wholly unavailable — abort, let caller 500 with
                # the count so far. Re-running restarts from scratch.
                raise
            except Exception:
                # Isolated per-object failure (over-length, transient 4xx,
                # ...). Leave the stale vector, keep going.
                failed += 1
                _ilog.warning("reembed row failed coll=%s id=%s", collection, r.get("id"))
                continue
            r2 = dict(r)
            r2["vector"] = vec
            await self._index.overwrite_rows(collection, [r2])
            processed += 1
            if on_progress is not None:
                on_progress(processed)
        _ilog.info(
            "reembed coll=%s rows=%d processed=%d failed=%d",
            collection, len(rows), processed, failed,
        )
        return (processed, failed)

    # ─── read ───

    async def search(self, collection: str, query: Query) -> list[Hit]:
        if self._index is None:
            return []
        t0 = time.monotonic()
        await self._index.ensure_fts_index(collection)
        qvec = (
            await self._embedder.embed_one(query.text)
            if query.text and query.text.strip() else None
        )
        rows = await self._index.search(
            collection, query.text, qvec, query.top_k,
            where_from_match(query.filters),
        )
        hits = [
            Hit(
                id=r["id"],
                score=float(r.get("_score", 0.0)),
                fields={k: v for k, v in r.items() if k not in NON_DOC_FIELDS},
            )
            for r in rows
        ]
        # query.log line: enough to tune top_k / spot pathological queries
        # without exposing the actual query text (which the business audit
        # log captures separately at logs/search/<UTC>.jsonl).
        ms = int((time.monotonic() - t0) * 1000)
        _qlog.info(
            "query coll=%s top_k=%d q_chars=%d filters=%s hits=%d ms=%d",
            collection, query.top_k, len(query.text or ""),
            ",".join(sorted(query.filters)) if query.filters else "",
            len(hits), ms,
        )
        return hits

    async def nearest(self, collection: str, text: str, top_k: int = 1) -> list[Hit]:
        """Pure-vector nearest-neighbour. Unlike :meth:`search` (hybrid
        FTS+vector with RRF — a rank-based fusion whose absolute score is
        tiny and NOT comparable to a fixed threshold), this embeds ``text``,
        retrieves the closest docs by vector distance, and returns a
        **true cosine similarity** ``score`` in [0, 1] (higher = closer),
        computed directly from the stored vectors. Computing cosine here
        (rather than trusting LanceDB's ``_distance``) makes the score
        metric-independent: the table uses LanceDB's default L2 on
        un-normalized embeddings, for which the ``1 - dist/2`` projection
        would NOT be a cosine. This is the thresholdable signal the
        session-mark write path uses to decide miss (new card) vs hit
        (link existing) — see ``searchbase_schema.CARD_ISSUE_HIT_THRESHOLD``."""
        if self._index is None:
            return []
        if not text or not text.strip():
            return []
        qvec = await self._embedder.embed_one(text)
        rows = await self._index.search(collection, "", qvec, top_k, None)
        scored: list[Hit] = []
        for r in rows:
            vec = r.get("vector")
            score = _cosine(qvec, vec) if vec is not None else 0.0
            scored.append(Hit(
                id=r["id"],
                score=score,
                fields={k: v for k, v in r.items() if k not in NON_DOC_FIELDS},
            ))
        # ANN order may not match true-cosine order exactly; sort by it.
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored

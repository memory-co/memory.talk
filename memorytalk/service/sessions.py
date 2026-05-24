"""IngestService — append-only round persistence with cursor-based concurrency.

Two methods:

  - ``ensure_session(req)`` — read-only. Returns the prefixed session id
    and the server's current ``(last_round_id, round_count)``. Lets sync
    decide where to resume from before reading the upstream file.

  - ``append_rounds(req)`` — write. Checks ``expected_prev_round_id``
    against the server's stored ``sessions.last_round_id``; appends the
    payload's rounds in order if they match, returns conflict with
    ``actual_last_round_id`` otherwise.

The old "diff against rounds_index by round_id + content hash" merge
logic is gone (alongside the ``rounds_index`` and ``ingest_log`` tables).
Sync now owns "what did I last hand over" via its own checkpoint DB and
``expected_prev_round_id``; we just trust the caller's delta and append.

Storage targets per append:

  jsonl on disk     — full round content (source of truth for read)
  SQLite sessions   — round_count + last_round_id cursor + metadata
  LanceDB rounds    — text + vector for FTS / semantic search
                      (best-effort; failure is logged but doesn't fail
                      the append — a follow-up rebuild can replay vectors)
"""
from __future__ import annotations
import datetime as _dt
import logging

from memorytalk.provider.embedding import Embedder
from memorytalk.provider.lancedb import LanceStore, _segment
from memorytalk.repository import SQLiteStore
from memorytalk.schemas import (
    AppendRoundsRequest, AppendRoundsResponse,
    EnsureSessionRequest, EnsureSessionResponse,
    RoundInput,
)
from memorytalk.service.events import EventWriter
from memorytalk.util.ids import prefix_session_id


_log = logging.getLogger("memorytalk.ingest")

# Cap fed into the embedder. Most local sentence-transformer models top
# out around 512 tokens (~2k chars of English / ~1k chars CJK); the OpenAI
# v3 embeddings tolerate 8k+ but we truncate the same way to keep ingest
# cost bounded. FTS stays on the FULL text — only the vector is built
# from the truncated prefix.
_EMBED_CHAR_LIMIT = 2000


class IngestServiceError(Exception):
    pass


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _flatten_text(blocks) -> str:
    """Pull plain text out of ContentBlocks for FTS + embedding.

    ``text`` / ``thinking`` blocks contribute their text. Non-text blocks
    fall back to a short type tag (``[tool_use]``, ``[tool_result]``) so
    the round at least has a marker — the row still gets FTS-indexed and
    keyword search can land on it.
    """
    parts: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("text") or b.get("thinking")
        if t:
            parts.append(str(t))
            continue
        ttype = b.get("type") or "block"
        parts.append(f"[{ttype}]")
    return "\n".join(parts)


def _embed_input(text: str) -> str:
    return text[:_EMBED_CHAR_LIMIT]


class IngestService:
    def __init__(
        self,
        db: SQLiteStore,
        vectors: LanceStore | None,
        embedder: Embedder | None,
        events: EventWriter,
    ):
        self.db = db
        self.vectors = vectors
        self.embedder = embedder
        self.events = events

    # ────────── ensure_session ──────────

    async def ensure_session(self, req: EnsureSessionRequest) -> EnsureSessionResponse:
        """Read-only probe — never creates rows. Returns where the
        server's cursor stands for this canonical session_id.

        Caller (sync watcher) is responsible for minting the canonical
        id via ``BaseAdapter.mint_session_id``; we accept it verbatim.
        Old code paths that handed in raw upstream ids go through
        ``prefix_session_id`` themselves (only the recall hook does
        this; see ``util/ids.py``).
        """
        sid = req.session_id
        existing = await self.db.sessions.get(sid)
        if existing is None:
            return EnsureSessionResponse(session_id=sid, last_round_id=None, round_count=0)
        return EnsureSessionResponse(
            session_id=sid,
            last_round_id=existing.get("last_round_id"),
            round_count=existing.get("round_count", 0),
        )

    # ────────── append_rounds ──────────

    async def append_rounds(self, req: AppendRoundsRequest) -> AppendRoundsResponse:
        # Canonical session_id arrives already minted by the caller
        # (sync watcher uses adapter.mint_session_id). No further
        # transformation here.
        sid = req.session_id
        now = _utc_iso()
        existing = await self.db.sessions.get(sid)
        server_last = existing.get("last_round_id") if existing else None

        # Optimistic-concurrency check. None on both sides means "no
        # session yet", which matches a fresh first append.
        if server_last != req.expected_prev_round_id:
            _log.info(
                "append_rounds conflict sid=%s expected=%s actual=%s",
                sid, req.expected_prev_round_id, server_last,
            )
            return AppendRoundsResponse(
                status="conflict",
                session_id=sid,
                actual_last_round_id=server_last,
            )

        if not req.rounds:
            # Cursor agrees with the caller, but the caller has nothing
            # to add. Refresh metadata + synced_at if the session exists;
            # nothing to do otherwise.
            if existing is not None:
                await self._refresh_meta(sid, req, existing, now)
            return AppendRoundsResponse(
                status="ok",
                session_id=sid,
                new_last_round_id=server_last,
                appended_count=0,
                round_count=existing.get("round_count", 0) if existing else 0,
            )

        existing_count = existing.get("round_count", 0) if existing else 0
        new_rounds = list(self._build_rounds(req.rounds, start_idx=existing_count + 1))
        cwd = req.metadata.get("cwd") if isinstance(req.metadata, dict) else None

        # 1. jsonl (source of truth) ------------------------------------
        await self.db.sessions.append_rounds_file(req.source, sid, new_rounds)

        # 2. sessions table + meta.json ---------------------------------
        new_total = existing_count + len(new_rounds)
        new_last = new_rounds[-1]["round_id"]
        if existing is None:
            await self.db.sessions.upsert(
                session_id=sid, source=req.source,
                location=req.location, location_label=req.location_label,
                cwd=cwd,
                created_at=req.created_at, synced_at=now,
                metadata=req.metadata, round_count=new_total,
                last_round_id=new_last,
            )
            await self.db.sessions.write_meta(req.source, sid, {
                "session_id": sid, "source": req.source,
                "created_at": req.created_at, "metadata": req.metadata,
                "round_count": new_total, "synced_at": now,
            })
        else:
            await self.db.sessions.update_after_append(sid, new_total, new_last, now)
            await self._refresh_meta(sid, req, existing, now,
                                     round_count_override=new_total)

        # 3. LanceDB rounds — best effort (per-batch isolated) -----------
        indexed_count, failed_idxs, index_err = await self._index_vectors(
            sid, req.source, new_rounds,
        )
        if not new_rounds:
            index_status = "ok"
        elif indexed_count == len(new_rounds):
            index_status = "ok"
        elif indexed_count == 0:
            index_status = "failed"
        else:
            index_status = "partial"

        await self.events.session_event(
            req.source, sid,
            "imported" if existing is None else "rounds_appended",
            added=len(new_rounds), round_count=new_total,
        )
        return AppendRoundsResponse(
            status="ok",
            session_id=sid,
            new_last_round_id=new_last,
            appended_count=len(new_rounds),
            round_count=new_total,
            indexed_count=indexed_count,
            index_failed_count=len(failed_idxs),
            index_status=index_status,
            index_error=index_err,
        )

    # ────────── helpers ──────────

    async def _refresh_meta(
        self,
        sid: str,
        req: AppendRoundsRequest,
        existing: dict,
        now: str,
        round_count_override: int | None = None,
    ) -> None:
        """Rewrite meta.json with the latest metadata + count. Cheap; we
        always do this on each append so downstream readers see fresh
        cwd / metadata values."""
        meta = await self.db.sessions.read_meta(req.source, sid) or {}
        meta.update({
            "session_id": sid, "source": req.source,
            "metadata": req.metadata or existing.get("metadata") or {},
            "round_count": (
                round_count_override
                if round_count_override is not None
                else existing.get("round_count", 0)
            ),
            "synced_at": now,
        })
        # created_at sticks once written.
        meta.setdefault("created_at", req.created_at or existing.get("created_at", ""))
        await self.db.sessions.write_meta(req.source, sid, meta)

    def _build_rounds(self, inputs: list[RoundInput], start_idx: int) -> list[dict]:
        rows: list[dict] = []
        idx = start_idx
        for r in inputs:
            content_dicts = [b.model_dump(exclude_none=True) for b in r.content]
            rows.append({
                "idx": idx,
                "round_id": r.round_id,
                "parent_id": r.parent_id,
                "timestamp": r.timestamp,
                "speaker": r.speaker,
                "role": r.role,
                "text": _flatten_text(content_dicts),
                "content": content_dicts,
                "is_sidechain": r.is_sidechain,
                "cwd": r.cwd,
                "usage": r.usage,
            })
            idx += 1
        return rows

    async def _index_vectors(
        self, sid: str, source: str, rows: list[dict],
    ) -> tuple[int, list[int], str | None]:
        """Embed + write LanceDB for ``rows``. Returns ``(succeeded,
        failed_idxs, last_err)``.

        Chunks at ``settings.embedding.batch_size`` so a single bad
        batch (e.g. DashScope's 10-cap 400) only loses that batch's
        rounds — earlier batches already flushed stay in LanceDB and
        their idxs go into ``sessions.indexed_round_count``. The
        background backfill loop will pick up the failed idxs on a
        future server start, so even with intermittent endpoint
        failures we'll converge.

        Caller passes the result onward via ``AppendRoundsResponse``
        so the sync watcher can surface it.
        """
        if self.vectors is None or self.embedder is None or not rows:
            return (0, [], None)

        # Mirror the embedder's batch_size so a chunk that lands in
        # ``embedder.embed()`` doesn't get re-chunked there (matches
        # endpoint cap exactly). Local / dummy embedders have no cap;
        # default to 100 — large enough to keep round-trip overhead low
        # and small enough to bound the blast radius of a bad batch.
        batch_size = getattr(self.embedder, "batch_size", 100)
        if not isinstance(batch_size, int) or batch_size < 1:
            batch_size = 100

        succeeded = 0
        failed_idxs: list[int] = []
        last_err: str | None = None
        now = _utc_iso()

        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            chunk_idxs = [r["idx"] for r in chunk]
            try:
                texts = [_embed_input(r["text"] or "") for r in chunk]
                vectors = await self.embedder.embed(texts)
                lance_rows = [
                    {
                        "session_id": sid,
                        "idx": r["idx"],
                        "role": r["role"] or "",
                        "text": _segment(r["text"] or ""),
                        "vector": v,
                    }
                    for r, v in zip(chunk, vectors)
                ]
                await self.vectors.add_rounds(lance_rows)
                succeeded += len(chunk)
                # Persist immediately so a crash mid-loop leaves the
                # SQLite counter accurate — backfill resumes from the
                # right offset.
                await self.db.sessions.bump_indexed_count(sid, len(chunk), now)
            except Exception as e:
                _log.exception(
                    "vector index batch failed sid=%s offset=%d size=%d",
                    sid, i, len(chunk),
                )
                failed_idxs.extend(chunk_idxs)
                last_err = str(e)

        if failed_idxs:
            await self.db.sessions.set_last_index_error(sid, last_err or "", now)
            await self.events.session_event(
                source, sid, "vector_index_failed",
                error=last_err, affected_indexes=failed_idxs,
            )

        return (succeeded, failed_idxs, last_err)

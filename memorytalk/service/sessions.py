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

from memorytalk.repository import SQLiteStore
from memorytalk.schemas import (
    AppendRoundsRequest, AppendRoundsResponse,
    EnsureSessionRequest, EnsureSessionResponse,
    RoundInput,
)
from memorytalk.searchbase import Doc, SearchBackend
from memorytalk.service.events import EventWriter
from memorytalk.service.searchbase_schema import ROUNDS, cap_text, round_doc_id
from memorytalk.util.instant import last_round_update_time


_log = logging.getLogger("memorytalk.ingest")


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


class IngestService:
    def __init__(
        self,
        db: SQLiteStore,
        search: SearchBackend | None,
        events: EventWriter,
    ):
        self.db = db
        self.search = search
        self.events = events

    # ────────── ensure_session ──────────

    async def ensure_session(self, req: EnsureSessionRequest) -> EnsureSessionResponse:
        """Read-only probe — never creates rows. Returns where the
        server's cursor stands for this canonical session_id.

        Caller (sync watcher) is responsible for minting the canonical
        id via ``BaseAdapter.mint_session_id``. The recall hook does
        its own minting via the adapter selected by ``--source`` /
        ``--location``; ``RecallService`` handles that and writes the
        already-canonicalized id, so callers here can rely on
        ``req.session_id`` being canonical.
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
        # Temporal high-water mark (explore's prior/posterior split keys
        # off it): max of the new rounds' timestamps and the prior value,
        # falling back to created_at then the ingest clock.
        lrut = last_round_update_time(
            [existing.get("last_round_update_time") if existing else None]
            + [r.timestamp for r in req.rounds],
            created_at=(existing.get("created_at") if existing else None) or req.created_at,
            synced_at=now,
        )
        if existing is None:
            await self.db.sessions.upsert(
                session_id=sid, source=req.source,
                location=req.location, location_label=req.location_label,
                cwd=cwd,
                created_at=req.created_at, synced_at=now,
                metadata=req.metadata, round_count=new_total,
                last_round_id=new_last, last_round_update_time=lrut,
            )
            await self.db.sessions.write_meta(req.source, sid, {
                "session_id": sid, "source": req.source,
                "created_at": req.created_at, "metadata": req.metadata,
                # Always include ``tags`` so meta.json has a uniform
                # shape from the very first write. Empty dict on create
                # since tagging only happens via PATCH after the fact.
                "tags": {},
                "round_count": new_total, "synced_at": now,
            })
        else:
            await self.db.sessions.update_after_append(
                sid, new_total, new_last, now, last_round_update_time=lrut,
            )
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
        cwd / metadata values.

        Tags are pulled from SQLite (the source of truth for
        user-supplied tags) and carried into the mirror. Without this,
        a ``PATCH /tags`` followed by an append would clobber the tags
        on disk — SQLite would keep them, but meta.json would lose
        them on every append, breaking the "files = full audit
        mirror" invariant.
        """
        meta = await self.db.sessions.read_meta(req.source, sid) or {}
        current_tags = await self.db.sessions.get_tags(sid) or {}
        meta.update({
            "session_id": sid, "source": req.source,
            "metadata": req.metadata or existing.get("metadata") or {},
            "tags": current_tags,
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
        """Index ``rows`` into searchbase. Returns ``(succeeded,
        failed_idxs, last_err)``.

        All-or-nothing per call: searchbase owns embedding + batching, so
        we hand it the whole batch as Docs. On failure the session stays
        degraded (round_count > indexed_round_count) and the background
        backfill loop retries it on a future pass, so we still converge.
        ``bump_indexed_count`` runs right after the durable upsert — no
        deferred flush, so the counter is accurate.

        Caller passes the result onward via ``AppendRoundsResponse`` so
        the sync watcher can surface it.
        """
        if self.search is None or not rows:
            return (0, [], None)

        now = _utc_iso()
        idxs = [r["idx"] for r in rows]
        try:
            docs = [
                Doc(
                    id=round_doc_id(sid, r["idx"]),
                    text=cap_text(r["text"]),
                    fields={
                        "session_id": sid,
                        "idx": r["idx"],
                        "role": r["role"] or "",
                    },
                )
                for r in rows
            ]
            await self.search.upsert(ROUNDS, docs)
            await self.db.sessions.bump_indexed_count(sid, len(rows), now)
            return (len(rows), [], None)
        except Exception as e:
            _log.exception(
                "vector index failed sid=%s rows=%d", sid, len(rows),
            )
            await self.db.sessions.set_last_index_error(sid, str(e), now)
            await self.events.session_event(
                source, sid, "vector_index_failed",
                error=str(e), affected_indexes=idxs,
            )
            return (0, idxs, str(e))

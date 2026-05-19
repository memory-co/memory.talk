"""IngestService — POST /v3/sessions implementation.

Writes go through three places in lockstep:

  jsonl file           — full round content (source of truth for read)
  rounds_index (SQL)   — {round_id → (idx, content_hash)} for ingest merge
  LanceDB rounds table — {session_id, idx, role, text, vector} for search

Merge rules (docs/api/v3/sessions.md):

  1. First ingest → assign 1, 2, 3, ... in request order.
  2. Re-ingest with same sha256 → skipped (no-op).
  3. Re-ingest with new sha256:
     - rounds matched by ``round_id`` with **identical content** keep
       their original ``idx``;
     - matched rounds whose content **changed** are *not* rewritten —
       they're recorded in ``overwrite_skipped`` and the original idx
       still points at the original content;
     - rounds not previously seen are appended with new indices, starting
       at ``max(existing idx) + 1`` (= session.round_count + 1).

This keeps card/review references stable forever once they're written.
"""
from __future__ import annotations
import datetime as _dt
import hashlib
import json

from memorytalk.provider.embedding import Embedder
from memorytalk.provider.lancedb import LanceStore, _segment
from memorytalk.repository import SQLiteStore
from memorytalk.schemas import (
    IngestSessionRequest, IngestSessionResponse, RoundInput,
)
from memorytalk.service.events import EventWriter
from memorytalk.util.ids import prefix_session_id


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


def _content_hash(content: list[dict]) -> str:
    """Stable hash of a round's content used to detect platform overwrites."""
    blob = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


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
    """Truncated prefix used as the embedder's input.

    FTS keeps the full text; only the vector is built from this prefix
    so long tool_result blocks don't blow up the embedder.
    """
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

    async def ingest(self, payload: IngestSessionRequest) -> IngestSessionResponse:
        sid = prefix_session_id(payload.session_id)
        now = _utc_iso()
        cwd = payload.metadata.get("cwd") if isinstance(payload.metadata, dict) else None

        existing = await self.db.sessions.get(sid)
        ingest = await self.db.sessions.get_ingest(sid)

        if existing and ingest and ingest["sha256"] == payload.sha256:
            return IngestSessionResponse(
                status="ok", session_id=sid, action="skipped",
                round_count=existing["round_count"],
            )

        if existing is None:
            return await self._first_ingest(sid, payload, cwd, now)
        return await self._merge_ingest(sid, payload, cwd, now, existing)

    # ────────── first ingest ──────────

    async def _first_ingest(
        self, sid: str, payload: IngestSessionRequest, cwd: str | None, now: str,
    ) -> IngestSessionResponse:
        rounds = list(self._build_rounds(payload.rounds, start_idx=1))
        await self._persist_rounds(
            session_id=sid, source=payload.source, rounds=rounds,
            create_meta=True, payload=payload, cwd=cwd, now=now,
            existing_round_count=0,
        )

        await self.db.sessions.upsert_ingest(sid, payload.sha256, now)
        await self.events.session_event(
            payload.source, sid, "imported",
            round_count=len(rounds), sha256=payload.sha256,
        )
        return IngestSessionResponse(
            status="ok", session_id=sid, action="imported",
            round_count=len(rounds), added_count=len(rounds),
        )

    # ────────── merge ingest ──────────

    async def _merge_ingest(
        self,
        sid: str,
        payload: IngestSessionRequest,
        cwd: str | None,
        now: str,
        existing: dict,
    ) -> IngestSessionResponse:
        # Existing rounds keyed by round_id → (idx, content_hash).
        stored = await self.db.sessions.get_round_index_map(sid)

        max_idx = existing["round_count"]
        new_inputs: list[RoundInput] = []
        new_indices: list[int] = []
        overwrite_skipped: list[int] = []

        for r in payload.rounds:
            content_dicts = [b.model_dump(exclude_none=True) for b in r.content]
            if r.round_id in stored:
                old_idx, old_hash = stored[r.round_id]
                new_hash = _content_hash(content_dicts)
                if new_hash != old_hash:
                    overwrite_skipped.append(old_idx)
                # Either way: append-only, never overwrite.
                continue
            max_idx += 1
            new_inputs.append(r)
            new_indices.append(max_idx)

        appended_rounds: list[dict] = []
        if new_inputs:
            appended_rounds = list(self._build_rounds_from_inputs(new_inputs, new_indices))

        added_count = len(appended_rounds)
        new_total = existing["round_count"] + added_count

        if appended_rounds:
            await self._persist_rounds(
                session_id=sid, source=payload.source, rounds=appended_rounds,
                create_meta=False, payload=payload, cwd=cwd, now=now,
                existing_round_count=existing["round_count"],
            )

        # Update session bookkeeping even for "nothing new" — ingest_log
        # records the new sha so a subsequent same-sha re-ingest skips.
        await self.db.sessions.update_round_count(sid, new_total, now)
        await self.db.sessions.upsert_ingest(sid, payload.sha256, now)

        # Refresh meta with the new count / latest metadata.
        meta = await self.db.sessions.read_meta(payload.source, sid) or {}
        meta.update({"round_count": new_total, "synced_at": now,
                     "metadata": payload.metadata})
        await self.db.sessions.write_meta(payload.source, sid, meta)

        if appended_rounds and overwrite_skipped:
            action = "partial_append"
        elif appended_rounds:
            action = "appended"
        else:
            # Either pure-skip (sha changed but nothing usable) or
            # overwrite-only (sha changed, every change is an overwrite).
            action = "skipped"

        if appended_rounds:
            await self.events.session_event(
                payload.source, sid, "rounds_appended",
                added=added_count, overwrite_skipped=overwrite_skipped,
            )
        if overwrite_skipped:
            await self.events.session_event(
                payload.source, sid, "rounds_overwrite_skipped",
                indexes=overwrite_skipped,
            )

        return IngestSessionResponse(
            status="ok", session_id=sid, action=action,
            round_count=new_total, added_count=added_count,
            overwrite_skipped=overwrite_skipped,
        )

    # ────────── helpers ──────────

    def _build_rounds(self, inputs, start_idx: int):
        """Yield stored-round dicts for a contiguous range of new inputs."""
        idx = start_idx
        for r in inputs:
            yield self._build_one(r, idx)
            idx += 1

    def _build_rounds_from_inputs(self, inputs, indices: list[int]):
        for r, idx in zip(inputs, indices):
            yield self._build_one(r, idx)

    def _build_one(self, r: RoundInput, idx: int) -> dict:
        content_dicts = [b.model_dump(exclude_none=True) for b in r.content]
        return {
            "idx": idx, "round_id": r.round_id, "parent_id": r.parent_id,
            "timestamp": r.timestamp, "speaker": r.speaker, "role": r.role,
            "text": _flatten_text(content_dicts),
            "content": content_dicts,
            "is_sidechain": r.is_sidechain, "cwd": r.cwd, "usage": r.usage,
            "content_hash": _content_hash(content_dicts),
        }

    async def _persist_rounds(
        self,
        session_id: str,
        source: str,
        rounds: list[dict],
        create_meta: bool,
        payload: IngestSessionRequest,
        cwd: str | None,
        now: str,
        existing_round_count: int,
    ) -> None:
        """Atomic-ish three-target write: jsonl, SQL index, LanceDB.

        Order matters: jsonl first (source of truth), then SQL index
        (so a future ingest with a same-sha shortcut works), then
        LanceDB (search index — last so a failure here doesn't corrupt
        ingest state; a follow-up rebuild can replay vectors).
        """
        new_total = existing_round_count + len(rounds)

        # 1. jsonl (file mirror, source of truth) ------------------------------
        await self.db.sessions.append_rounds_file(source, session_id, rounds)

        # 2. session table + meta + rounds_index ------------------------------
        if create_meta:
            await self.db.sessions.write_meta(source, session_id, {
                "session_id": session_id, "source": source,
                "created_at": payload.created_at, "metadata": payload.metadata,
                "round_count": new_total, "synced_at": now,
            })
            await self.db.sessions.upsert(
                session_id=session_id, source=source, cwd=cwd,
                created_at=payload.created_at, synced_at=now,
                metadata=payload.metadata, round_count=new_total,
            )

        await self.db.sessions.upsert_rounds_index(
            (session_id, r["round_id"], r["idx"], r["content_hash"])
            for r in rounds
        )

        # 3. LanceDB rounds (FTS + vector) ------------------------------------
        if self.vectors is not None and self.embedder is not None:
            try:
                texts = [_embed_input(r["text"] or "") for r in rounds]
                vectors = await self.embedder.embed(texts) if texts else []
                lance_rows = [
                    {
                        "session_id": session_id,
                        "idx": r["idx"],
                        "role": r["role"] or "",
                        "text": _segment(r["text"] or ""),
                        "vector": v,
                    }
                    for r, v in zip(rounds, vectors)
                ]
                await self.vectors.add_rounds(lance_rows)
            except Exception as e:
                # LanceDB write is best-effort — don't fail ingest. The
                # round is searchable as soon as a follow-up rebuild
                # writes the missing rows. We still emit an event so
                # `sync status.recent` can show the warning.
                await self.events.session_event(
                    source, session_id, "vector_index_failed",
                    error=str(e), affected_indexes=[r["idx"] for r in rounds],
                )

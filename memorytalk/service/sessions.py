"""Session service — ingest (write), view / log (read). All async.

Tag operations live in TagService (memorytalk/service/tags.py). SessionService
holds a reference to TagService so ingest can stamp `sync_session: new`
or `sync_session: update` on each successful sync action — fueling the
built-in ``new-session`` filter's "what got synced and isn't yet
processed" view.
"""
from __future__ import annotations
import json
from typing import TYPE_CHECKING, Any

from memorytalk.config import Config
from memorytalk.provider.lancedb import LanceStore
from memorytalk.repository import SQLiteStore
from memorytalk.schemas import (
    ContentBlock, EventEntry, IngestRound, IngestSessionRequest,
    IngestSessionResponse, LogResponse, SessionRound, SessionView, TagPair,
    ViewResponse,
)
from memorytalk.service.events import EventWriter
from memorytalk.service.links import link_to_ref, refresh_active_user_links
from memorytalk.util.ids import SESSION_PREFIX, prefix_session_id
from memorytalk.util.ttl import dt_to_iso, now_utc

if TYPE_CHECKING:
    # Late-binding to avoid circular import — TagService imports SessionNotFound
    # from this module, so we cannot import TagService at module load time.
    from memorytalk.service.tags import TagService


class SessionServiceError(ValueError):
    """400 — validation / type-mismatch errors."""


class SessionNotFound(SessionServiceError):
    """404 — session id is well-formed but doesn't exist."""


def _content_text(content: list[ContentBlock] | list[dict]) -> str:
    """Works on either Pydantic list or dict list (rebuild replays from jsonl dicts)."""
    parts: list[str] = []
    for b in content or []:
        if isinstance(b, ContentBlock):
            t = b.type
            txt = b.text or ""
            thinking = b.thinking or ""
        else:
            t = b.get("type")
            txt = b.get("text") or ""
            thinking = b.get("thinking") or ""
        if t in ("text", "code") and txt:
            parts.append(txt)
        elif t == "thinking" and thinking:
            parts.append(thinking)
    return "\n".join(parts)


def _rounds_to_text(rounds: list[dict]) -> str:
    return "\n".join(_content_text(r.get("content") or []) for r in rounds)


def _round_content_key(content: list[ContentBlock] | list[dict]) -> str:
    """Canonical form of content blocks for overwrite-detection equality."""
    as_dicts = [b.model_dump() if isinstance(b, ContentBlock) else b for b in content or []]
    return json.dumps(as_dicts, ensure_ascii=False, sort_keys=True)


class SessionService:
    def __init__(
        self, *,
        config: Config,
        db: SQLiteStore,
        vectors: LanceStore,
        events: EventWriter,
        tags: "TagService",
    ):
        self.config = config
        self.db = db
        self.vectors = vectors
        self.events = events
        self.tags = tags

    async def _stamp_sync_tag(self, session_id: str, value: str) -> None:
        """Write `sync_session: <value>` via TagService (so sqlite +
        tags.json mirror + tag_added/tag_updated events all stay in
        sync). Called from ingest() after each successful action."""
        await self.tags.add_tags(session_id, [f"sync_session:{value}"])

    # -------- writes --------

    async def ingest(self, payload: IngestSessionRequest) -> IngestSessionResponse:
        raw_id = payload.session_id
        if not raw_id:
            raise SessionServiceError("session_id required")
        source = payload.source
        if not source:
            raise SessionServiceError("source required")
        sha256 = payload.sha256 or ""

        session_id = prefix_session_id(raw_id)
        created_at = payload.created_at or dt_to_iso(now_utc())
        metadata = payload.metadata
        now_iso = dt_to_iso(now_utc())

        existing_meta = await self.db.sessions.read_meta(source, session_id)
        if sha256 and existing_meta and existing_meta.get("last_sha256") == sha256:
            existing = await self.db.sessions.get(session_id)
            return IngestSessionResponse(
                status="ok", session_id=session_id, action="skipped",
                round_count=existing["round_count"] if existing else 0,
                added_count=0, overwrite_skipped=[],
            )

        existing = await self.db.sessions.get(session_id)

        if existing is None:
            assigned = [self._assign_round(r, idx=i) for i, r in enumerate(payload.rounds, start=1)]

            meta_new: dict[str, Any] = {
                "session_id": session_id, "source": source, "created_at": created_at,
                "metadata": metadata, "round_count": len(assigned),
                "synced_at": now_iso,
            }
            if sha256:
                meta_new["last_sha256"] = sha256
            await self.db.sessions.write_meta(source, session_id, meta_new)
            await self.db.sessions.append_rounds_file(source, session_id, assigned)

            await self.db.sessions.upsert(
                session_id=session_id, source=source, created_at=created_at,
                synced_at=now_iso, metadata=metadata, round_count=len(assigned),
            )
            await self.db.sessions.upsert_rounds(session_id, assigned)
            await self.vectors.add_session(session_id, _rounds_to_text(assigned))

            await self.events.emit(session_id, "imported", {
                "source": source, "round_count": len(assigned),
            })
            await self._stamp_sync_tag(session_id, "new")

            return IngestSessionResponse(
                status="ok", session_id=session_id, action="imported",
                round_count=len(assigned), added_count=len(assigned),
                overwrite_skipped=[],
            )

        # Append path
        if existing["source"] != source:
            raise SessionServiceError(
                f"source mismatch: existing={existing['source']!r}, new={source!r}"
            )

        existing_rounds = await self.db.sessions.list_rounds(session_id)
        by_round_id = {r["round_id"]: r for r in existing_rounds}
        next_idx = (await self.db.sessions.max_round_idx(session_id)) + 1

        appended: list[dict] = []
        overwrite_skipped: list[int] = []

        for r in payload.rounds:
            rid = r.round_id
            if rid in by_round_id:
                old = by_round_id[rid]
                old_key = (old["role"], old["speaker"], _round_content_key(old["content"]))
                new_key = (r.role, r.speaker, _round_content_key(r.content))
                if old_key == new_key:
                    continue
                overwrite_skipped.append(old["idx"])
                continue
            appended.append(self._assign_round(r, idx=next_idx))
            next_idx += 1

        total_count = existing["round_count"] + len(appended)

        if appended:
            await self.db.sessions.append_rounds_file(source, session_id, appended)
            await self.db.sessions.upsert_rounds(session_id, appended)
            await self.db.sessions.update_round_count(session_id, total_count, now_iso)
            all_rounds = await self.db.sessions.list_rounds(session_id)
            await self.vectors.add_session(session_id, _rounds_to_text(all_rounds))

        meta_existing = await self.db.sessions.read_meta(source, session_id) or {}
        meta_existing.update({"round_count": total_count, "synced_at": now_iso})
        if sha256:
            meta_existing["last_sha256"] = sha256
        await self.db.sessions.write_meta(source, session_id, meta_existing)

        if appended and not overwrite_skipped:
            action = "appended"
            await self.events.emit(session_id, "rounds_appended", {
                "from_index": appended[0]["idx"], "to_index": appended[-1]["idx"],
                "added_count": len(appended),
            })
        elif appended and overwrite_skipped:
            action = "partial_append"
            await self.events.emit(session_id, "rounds_appended", {
                "from_index": appended[0]["idx"], "to_index": appended[-1]["idx"],
                "added_count": len(appended),
            })
            await self.events.emit(session_id, "rounds_overwrite_skipped", {"indexes": overwrite_skipped})
        elif overwrite_skipped:
            action = "partial_append"
            await self.events.emit(session_id, "rounds_overwrite_skipped", {"indexes": overwrite_skipped})
        else:
            action = "skipped"

        # Stamp sync_session tag for any action that materialized changes.
        # `skipped` (no rounds touched) leaves the existing tag alone.
        if action in ("appended", "partial_append"):
            await self._stamp_sync_tag(session_id, "update")

        return IngestSessionResponse(
            status="ok", session_id=session_id, action=action,
            round_count=total_count, added_count=len(appended),
            overwrite_skipped=overwrite_skipped,
        )

    @staticmethod
    def _assign_round(r: IngestRound, *, idx: int) -> dict:
        """Turn an IngestRound request item into the dict shape stored in
        rounds.jsonl and SQLite. Content is JSON-serialized via model_dump."""
        return {
            "idx": idx,
            "round_id": r.round_id,
            "parent_id": r.parent_id,
            "timestamp": r.timestamp,
            "speaker": r.speaker,
            "role": r.role,
            "content": [b.model_dump() for b in r.content],
            "is_sidechain": r.is_sidechain,
            "cwd": r.cwd,
            "usage": r.usage,
        }

    # -------- reads --------

    async def view(self, session_id: str) -> ViewResponse:
        if not session_id.startswith(SESSION_PREFIX):
            raise SessionServiceError("invalid session_id prefix")
        session = await self.db.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(f"session not found: {session_id}")
        rounds = await self.db.sessions.list_rounds(session_id)

        now = now_utc()
        links = await self.db.links.touching(session_id)
        await refresh_active_user_links(
            self.db, links,
            factor=self.config.settings.ttl.link.factor,
            max_seconds=self.config.settings.ttl.link.max,
            now=now,
        )

        tag_pairs = await self.db.tags.list_for_subject(session_id)

        return ViewResponse(
            type="session",
            read_at=dt_to_iso(now),
            session=SessionView(
                session_id=session["session_id"],
                source=session["source"],
                created_at=session["created_at"],
                tags=[TagPair(**p) for p in tag_pairs],
                metadata=session["metadata"],
                rounds=[SessionRound(
                    index=r["idx"], round_id=r["round_id"], parent_id=r["parent_id"],
                    timestamp=r["timestamp"], speaker=r["speaker"], role=r["role"],
                    content=r["content"], is_sidechain=r["is_sidechain"],
                    cwd=r["cwd"], usage=r["usage"],
                ) for r in rounds],
            ),
            links=[link_to_ref(l, session_id, now) for l in links],
        )

    async def log(self, session_id: str) -> LogResponse:
        if not session_id.startswith(SESSION_PREFIX):
            raise SessionServiceError("invalid session_id prefix")
        session = await self.db.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(f"session not found: {session_id}")
        events = await self.db.sessions.read_events(session["source"], session_id)
        events.sort(key=lambda e: e["at"])
        return LogResponse(
            type="session",
            session_id=session_id,
            events=[EventEntry(at=e["at"], kind=e["kind"], detail=e["detail"]) for e in events],
        )


"""Session service — ingest (write), view / log (read), tag add/remove. All async."""
from __future__ import annotations
import json
from typing import Any

from memory_talk_v2.config import Config
from memory_talk_v2.ids import SESSION_PREFIX, prefix_session_id
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.service.links import link_to_ref, refresh_active_user_links
from memory_talk_v2.service.ttl import dt_to_iso, now_utc
from memory_talk_v2.storage import files as F
from memory_talk_v2.storage.lancedb import LanceStore
from memory_talk_v2.storage.sqlite import SQLiteStore


class SessionServiceError(ValueError):
    """400 — validation / type-mismatch errors."""


class SessionNotFound(SessionServiceError):
    """404 — session id is well-formed but doesn't exist."""


def _content_text(content: list[dict]) -> str:
    parts: list[str] = []
    for b in content or []:
        t = b.get("type")
        if t in ("text", "code"):
            parts.append(b.get("text") or "")
        elif t == "thinking":
            parts.append(b.get("thinking") or "")
    return "\n".join(p for p in parts if p)


def _rounds_to_text(rounds: list[dict]) -> str:
    return "\n".join(_content_text(r.get("content") or []) for r in rounds)


def _round_key(r: dict) -> tuple:
    return (
        r.get("role"),
        r.get("speaker"),
        json.dumps(r.get("content") or [], ensure_ascii=False, sort_keys=True),
    )


class SessionService:
    def __init__(
        self, *,
        config: Config,
        db: SQLiteStore,
        vectors: LanceStore,
        events: EventWriter,
    ):
        self.config = config
        self.db = db
        self.vectors = vectors
        self.events = events

    # -------- writes --------

    async def ingest(self, payload: dict) -> dict:
        raw_id = payload.get("session_id") or ""
        if not raw_id:
            raise SessionServiceError("session_id required")
        source = payload.get("source") or ""
        if not source:
            raise SessionServiceError("source required")
        sha256 = payload.get("sha256") or ""

        session_id = prefix_session_id(raw_id)
        created_at = payload.get("created_at") or dt_to_iso(now_utc())
        metadata = payload.get("metadata") or {}
        in_rounds: list[dict] = payload.get("rounds") or []
        now_iso = dt_to_iso(now_utc())

        existing_meta = await F.read_session_meta(self.config.sessions_dir, source, session_id)
        if sha256 and existing_meta and existing_meta.get("last_sha256") == sha256:
            existing = await self.db.get_session(session_id)
            return {
                "status": "ok", "session_id": session_id, "action": "skipped",
                "round_count": existing["round_count"] if existing else 0,
                "added_count": 0, "overwrite_skipped": [],
            }

        existing = await self.db.get_session(session_id)

        if existing is None:
            assigned = []
            for i, r in enumerate(in_rounds, start=1):
                assigned.append({
                    "idx": i,
                    "round_id": r.get("round_id") or "",
                    "parent_id": r.get("parent_id"),
                    "timestamp": r.get("timestamp"),
                    "speaker": r.get("speaker"),
                    "role": r.get("role"),
                    "content": r.get("content") or [],
                    "is_sidechain": bool(r.get("is_sidechain")),
                    "cwd": r.get("cwd"),
                    "usage": r.get("usage"),
                })

            meta_new: dict[str, Any] = {
                "session_id": session_id, "source": source, "created_at": created_at,
                "metadata": metadata, "tags": [], "round_count": len(assigned),
                "synced_at": now_iso,
            }
            if sha256:
                meta_new["last_sha256"] = sha256
            await F.write_session_meta(self.config.sessions_dir, source, session_id, meta_new)
            await F.append_session_rounds(self.config.sessions_dir, source, session_id, assigned)

            await self.db.upsert_session(
                session_id=session_id, source=source, created_at=created_at,
                synced_at=now_iso, metadata=metadata, tags=[], round_count=len(assigned),
            )
            await self.db.upsert_rounds(session_id, assigned)
            await self.vectors.add_session(session_id, _rounds_to_text(assigned))

            await self.events.emit(session_id, "imported", {
                "source": source, "round_count": len(assigned),
            })

            return {
                "status": "ok", "session_id": session_id, "action": "imported",
                "round_count": len(assigned), "added_count": len(assigned),
                "overwrite_skipped": [],
            }

        # Append path
        if existing["source"] != source:
            raise SessionServiceError(
                f"source mismatch: existing={existing['source']!r}, new={source!r}"
            )

        existing_rounds = await self.db.list_rounds(session_id)
        by_round_id = {r["round_id"]: r for r in existing_rounds}
        next_idx = (await self.db.max_round_idx(session_id)) + 1

        appended: list[dict] = []
        overwrite_skipped: list[int] = []

        for r in in_rounds:
            rid = r.get("round_id") or ""
            if rid in by_round_id:
                old = by_round_id[rid]
                old_key = (
                    old.get("role"), old.get("speaker"),
                    json.dumps(old.get("content") or [], ensure_ascii=False, sort_keys=True),
                )
                if old_key == _round_key(r):
                    continue
                overwrite_skipped.append(old["idx"])
                continue
            appended.append({
                "idx": next_idx,
                "round_id": rid,
                "parent_id": r.get("parent_id"),
                "timestamp": r.get("timestamp"),
                "speaker": r.get("speaker"),
                "role": r.get("role"),
                "content": r.get("content") or [],
                "is_sidechain": bool(r.get("is_sidechain")),
                "cwd": r.get("cwd"),
                "usage": r.get("usage"),
            })
            next_idx += 1

        total_count = existing["round_count"] + len(appended)

        if appended:
            await F.append_session_rounds(self.config.sessions_dir, source, session_id, appended)
            await self.db.upsert_rounds(session_id, appended)
            await self.db.update_session_round_count(session_id, total_count, now_iso)
            all_rounds = await self.db.list_rounds(session_id)
            await self.vectors.add_session(session_id, _rounds_to_text(all_rounds))

        meta_existing = await F.read_session_meta(self.config.sessions_dir, source, session_id) or {}
        meta_existing.update({"round_count": total_count, "synced_at": now_iso})
        if sha256:
            meta_existing["last_sha256"] = sha256
        await F.write_session_meta(self.config.sessions_dir, source, session_id, meta_existing)

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

        return {
            "status": "ok", "session_id": session_id, "action": action,
            "round_count": total_count, "added_count": len(appended),
            "overwrite_skipped": overwrite_skipped,
        }

    # -------- reads --------

    async def view(self, session_id: str) -> dict:
        if not session_id.startswith(SESSION_PREFIX):
            raise SessionServiceError("invalid session_id prefix")
        session = await self.db.get_session(session_id)
        if session is None:
            raise SessionNotFound(f"session not found: {session_id}")
        rounds = await self.db.list_rounds(session_id)

        now = now_utc()
        links = await self.db.links_touching(session_id)
        await refresh_active_user_links(
            self.db, links,
            factor=self.config.settings.ttl.link.factor,
            max_seconds=self.config.settings.ttl.link.max,
            now=now,
        )

        return {
            "type": "session",
            "read_at": dt_to_iso(now),
            "session": {
                "session_id": session["session_id"],
                "source": session["source"],
                "created_at": session["created_at"],
                "tags": session["tags"],
                "metadata": session["metadata"],
                "rounds": [{
                    "index": r["idx"], "round_id": r["round_id"], "parent_id": r["parent_id"],
                    "timestamp": r["timestamp"], "speaker": r["speaker"], "role": r["role"],
                    "content": r["content"], "is_sidechain": r["is_sidechain"],
                    "cwd": r["cwd"], "usage": r["usage"],
                } for r in rounds],
            },
            "links": [link_to_ref(l, session_id, now) for l in links],
        }

    async def log(self, session_id: str) -> dict:
        if not session_id.startswith(SESSION_PREFIX):
            raise SessionServiceError("invalid session_id prefix")
        session = await self.db.get_session(session_id)
        if session is None:
            raise SessionNotFound(f"session not found: {session_id}")
        events = await F.read_session_events(
            self.config.sessions_dir, session["source"], session_id,
        )
        events.sort(key=lambda e: e["at"])
        return {
            "type": "session",
            "session_id": session_id,
            "events": [{"at": e["at"], "kind": e["kind"], "detail": e["detail"]} for e in events],
        }

    # -------- tags --------

    async def add_tags(self, payload: dict) -> dict:
        session_id = payload.get("session_id") or ""
        incoming = payload.get("tags") or []
        if not isinstance(incoming, list) or not all(isinstance(t, str) and t for t in incoming):
            raise SessionServiceError("tags must be a non-empty list of strings")
        session = await self._require_session(session_id, "tag only applies to sessions")

        existing = list(session["tags"])
        newly_added = [t for t in incoming if t not in existing]
        ordered = existing + [t for t in newly_added if t not in existing]

        await self._persist_tags(session, ordered)
        now_iso = dt_to_iso(now_utc())
        for t in newly_added:
            await self.events.emit(session_id, "tag_added", {"tag": t}, at=now_iso)
        return {"status": "ok", "tags": ordered}

    async def remove_tags(self, payload: dict) -> dict:
        session_id = payload.get("session_id") or ""
        incoming = payload.get("tags") or []
        if not isinstance(incoming, list) or not all(isinstance(t, str) and t for t in incoming):
            raise SessionServiceError("tags must be a non-empty list of strings")
        session = await self._require_session(session_id, "tag only applies to sessions")

        existing = list(session["tags"])
        removal_set = set(incoming)
        truly_removed = [t for t in existing if t in removal_set]
        remaining = [t for t in existing if t not in removal_set]

        await self._persist_tags(session, remaining)
        now_iso = dt_to_iso(now_utc())
        for t in truly_removed:
            await self.events.emit(session_id, "tag_removed", {"tag": t}, at=now_iso)
        return {"status": "ok", "tags": remaining}

    async def _require_session(self, session_id: str, type_error_msg: str) -> dict:
        if not session_id.startswith(SESSION_PREFIX):
            raise SessionServiceError(f"type mismatch: {type_error_msg}")
        s = await self.db.get_session(session_id)
        if s is None:
            raise SessionNotFound(f"session not found: {session_id}")
        return s

    async def _persist_tags(self, session: dict, tags: list[str]) -> None:
        await self.db.update_session_tags(session["session_id"], tags)
        meta = await F.read_session_meta(
            self.config.sessions_dir, session["source"], session["session_id"]
        ) or {}
        meta["tags"] = tags
        await F.write_session_meta(
            self.config.sessions_dir, session["source"], session["session_id"], meta
        )

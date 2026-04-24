"""Session service — ingest (write), view / log (read), tag add/remove.

Ingest path (spec §3.1): sha256 fast-path via meta.last_sha256, then
round_id-based append with overwrite detection. rounds.jsonl is append-only.

View path (spec §3.6): reads session + rounds + links, refreshes active
user links touching this session (sessions themselves have no TTL).

Log path: reads per-session events.jsonl.

Tag path: diff-based event emission, per-tag granularity.
"""
from __future__ import annotations
import json
from typing import Any

from memory_talk_v2.ids import SESSION_PREFIX, prefix_session_id
from memory_talk_v2.service.context import ServiceContext
from memory_talk_v2.service.links import link_to_ref, refresh_active_user_links
from memory_talk_v2.service.ttl import dt_to_iso, now_utc
from memory_talk_v2.storage import files as F


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
    """Content-equality key for overwrite detection (ignores timestamp)."""
    return (
        r.get("role"),
        r.get("speaker"),
        json.dumps(r.get("content") or [], ensure_ascii=False, sort_keys=True),
    )


class SessionService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx

    # -------- writes --------

    def ingest(self, payload: dict) -> dict:
        ctx = self.ctx
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

        # sha256 fast-path: skip if the client-provided hash matches the last
        # recorded one on meta.json.
        existing_meta = F.read_session_meta(ctx.config.sessions_dir, source, session_id)
        if sha256 and existing_meta and existing_meta.get("last_sha256") == sha256:
            existing = ctx.db.get_session(session_id)
            return {
                "status": "ok", "session_id": session_id, "action": "skipped",
                "round_count": existing["round_count"] if existing else 0,
                "added_count": 0, "overwrite_skipped": [],
            }

        existing = ctx.db.get_session(session_id)

        if existing is None:
            # First ingest
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
            F.write_session_meta(ctx.config.sessions_dir, source, session_id, meta_new)
            F.append_session_rounds(ctx.config.sessions_dir, source, session_id, assigned)

            ctx.db.upsert_session(
                session_id=session_id, source=source, created_at=created_at,
                synced_at=now_iso, metadata=metadata, tags=[], round_count=len(assigned),
            )
            ctx.db.upsert_rounds(session_id, assigned)
            ctx.vectors.add_session(session_id, _rounds_to_text(assigned))

            ctx.events.emit(session_id, "imported", {
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

        existing_rounds = ctx.db.list_rounds(session_id)
        by_round_id = {r["round_id"]: r for r in existing_rounds}
        next_idx = ctx.db.max_round_idx(session_id) + 1

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
            F.append_session_rounds(ctx.config.sessions_dir, source, session_id, appended)
            ctx.db.upsert_rounds(session_id, appended)
            ctx.db.update_session_round_count(session_id, total_count, now_iso)
            all_rounds = ctx.db.list_rounds(session_id)
            ctx.vectors.add_session(session_id, _rounds_to_text(all_rounds))

        meta_existing = F.read_session_meta(ctx.config.sessions_dir, source, session_id) or {}
        meta_existing.update({"round_count": total_count, "synced_at": now_iso})
        if sha256:
            meta_existing["last_sha256"] = sha256
        F.write_session_meta(ctx.config.sessions_dir, source, session_id, meta_existing)

        if appended and not overwrite_skipped:
            action = "appended"
            ctx.events.emit(session_id, "rounds_appended", {
                "from_index": appended[0]["idx"], "to_index": appended[-1]["idx"],
                "added_count": len(appended),
            })
        elif appended and overwrite_skipped:
            action = "partial_append"
            ctx.events.emit(session_id, "rounds_appended", {
                "from_index": appended[0]["idx"], "to_index": appended[-1]["idx"],
                "added_count": len(appended),
            })
            ctx.events.emit(session_id, "rounds_overwrite_skipped", {"indexes": overwrite_skipped})
        elif overwrite_skipped:
            action = "partial_append"
            ctx.events.emit(session_id, "rounds_overwrite_skipped", {"indexes": overwrite_skipped})
        else:
            action = "skipped"

        return {
            "status": "ok", "session_id": session_id, "action": action,
            "round_count": total_count, "added_count": len(appended),
            "overwrite_skipped": overwrite_skipped,
        }

    # -------- reads --------

    def view(self, session_id: str) -> dict:
        ctx = self.ctx
        if not session_id.startswith(SESSION_PREFIX):
            raise SessionServiceError("invalid session_id prefix")
        session = ctx.db.get_session(session_id)
        if session is None:
            raise SessionNotFound(f"session not found: {session_id}")
        rounds = ctx.db.list_rounds(session_id)

        now = now_utc()
        links = ctx.db.links_touching(session_id)
        refresh_active_user_links(
            ctx.db, links,
            factor=ctx.config.settings.ttl.link.factor,
            max_seconds=ctx.config.settings.ttl.link.max,
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

    def log(self, session_id: str) -> dict:
        ctx = self.ctx
        if not session_id.startswith(SESSION_PREFIX):
            raise SessionServiceError("invalid session_id prefix")
        session = ctx.db.get_session(session_id)
        if session is None:
            raise SessionNotFound(f"session not found: {session_id}")
        events = F.read_session_events(
            ctx.config.sessions_dir, session["source"], session_id,
        )
        events.sort(key=lambda e: e["at"])
        return {
            "type": "session",
            "session_id": session_id,
            "events": [{"at": e["at"], "kind": e["kind"], "detail": e["detail"]} for e in events],
        }

    # -------- tags --------

    def add_tags(self, payload: dict) -> dict:
        session_id = payload.get("session_id") or ""
        incoming = payload.get("tags") or []
        if not isinstance(incoming, list) or not all(isinstance(t, str) and t for t in incoming):
            raise SessionServiceError("tags must be a non-empty list of strings")
        session = self._require_session(session_id, "tag only applies to sessions")

        existing = list(session["tags"])
        newly_added = [t for t in incoming if t not in existing]
        ordered = existing + [t for t in newly_added if t not in existing]

        self._persist_tags(session, ordered)
        now_iso = dt_to_iso(now_utc())
        for t in newly_added:
            self.ctx.events.emit(session_id, "tag_added", {"tag": t}, at=now_iso)
        return {"status": "ok", "tags": ordered}

    def remove_tags(self, payload: dict) -> dict:
        session_id = payload.get("session_id") or ""
        incoming = payload.get("tags") or []
        if not isinstance(incoming, list) or not all(isinstance(t, str) and t for t in incoming):
            raise SessionServiceError("tags must be a non-empty list of strings")
        session = self._require_session(session_id, "tag only applies to sessions")

        existing = list(session["tags"])
        removal_set = set(incoming)
        truly_removed = [t for t in existing if t in removal_set]
        remaining = [t for t in existing if t not in removal_set]

        self._persist_tags(session, remaining)
        now_iso = dt_to_iso(now_utc())
        for t in truly_removed:
            self.ctx.events.emit(session_id, "tag_removed", {"tag": t}, at=now_iso)
        return {"status": "ok", "tags": remaining}

    def _require_session(self, session_id: str, type_error_msg: str) -> dict:
        if not session_id.startswith(SESSION_PREFIX):
            raise SessionServiceError(f"type mismatch: {type_error_msg}")
        s = self.ctx.db.get_session(session_id)
        if s is None:
            raise SessionNotFound(f"session not found: {session_id}")
        return s

    def _persist_tags(self, session: dict, tags: list[str]) -> None:
        ctx = self.ctx
        ctx.db.update_session_tags(session["session_id"], tags)
        meta = F.read_session_meta(
            ctx.config.sessions_dir, session["source"], session["session_id"]
        ) or {}
        meta["tags"] = tags
        F.write_session_meta(
            ctx.config.sessions_dir, session["source"], session["session_id"], meta
        )

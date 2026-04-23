"""Sessions ingest service — sha256 dedupe, index assignment, overwrite detection.

Design decisions (see spec §3.1):
- rounds.jsonl is append-only forever; overwrite-detected rounds are skipped, not rewritten
- content_equal compares content (JSON) + role + speaker, ignoring timestamp
- action: imported / appended / skipped / partial_append
- rounds_overwrite_skipped event emitted once per ingest with detail.indexes = list
"""
from __future__ import annotations
import json
from typing import Any

from memory_talk_v2.ids import prefix_session_id
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.service.ttl import dt_to_iso, now_utc
from memory_talk_v2.storage import files as F
from memory_talk_v2.storage.lancedb import LanceStore
from memory_talk_v2.storage.sqlite import SQLiteStore


class SessionServiceError(ValueError):
    """Validation errors raised by the sessions service."""


def _content_text(content: list[dict]) -> str:
    parts: list[str] = []
    for b in content or []:
        t = b.get("type")
        if t == "text" or t == "code":
            parts.append(b.get("text") or "")
        elif t == "thinking":
            parts.append(b.get("thinking") or "")
    return "\n".join(p for p in parts if p)


def _rounds_to_session_text(rounds: list[dict]) -> str:
    return "\n".join(_content_text(r.get("content") or []) for r in rounds)


def _round_key(r: dict) -> tuple:
    """Content-equality key for overwrite detection (ignores timestamp)."""
    return (
        r.get("role"),
        r.get("speaker"),
        json.dumps(r.get("content") or [], ensure_ascii=False, sort_keys=True),
    )


def ingest_session(
    payload: dict,
    *,
    db: SQLiteStore,
    vectors: LanceStore,
    events: EventWriter,
    sessions_root,
) -> dict:
    raw_id = payload.get("session_id") or ""
    if not raw_id:
        raise SessionServiceError("session_id required")
    source = payload.get("source") or ""
    if not source:
        raise SessionServiceError("source required")
    sha256 = payload.get("sha256") or ""  # optional perf hint; not required

    session_id = prefix_session_id(raw_id)
    created_at = payload.get("created_at") or dt_to_iso(now_utc())
    metadata = payload.get("metadata") or {}
    in_rounds: list[dict] = payload.get("rounds") or []
    now_iso = dt_to_iso(now_utc())

    # sha256 fast-path: if the client provided a hash and it matches the last
    # recorded one on meta.json, nothing in the file has changed — skip without
    # parsing rounds. File is the source of truth; rebuild restores last_sha256.
    existing_meta = F.read_session_meta(sessions_root, source, session_id)
    if sha256 and existing_meta and existing_meta.get("last_sha256") == sha256:
        existing = db.get_session(session_id)
        return {
            "status": "ok",
            "session_id": session_id,
            "action": "skipped",
            "round_count": existing["round_count"] if existing else 0,
            "added_count": 0,
            "overwrite_skipped": [],
        }

    existing = db.get_session(session_id)

    if existing is None:
        # First ingest — enforce source match is moot; just write
        assigned = []
        for i, r in enumerate(in_rounds, start=1):
            rec = {
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
            }
            assigned.append(rec)

        # Write files first (rounds.jsonl append), then SQLite
        meta_new = {
            "session_id": session_id, "source": source, "created_at": created_at,
            "metadata": metadata, "tags": [], "round_count": len(assigned),
            "synced_at": now_iso,
        }
        if sha256:
            meta_new["last_sha256"] = sha256
        F.write_session_meta(sessions_root, source, session_id, meta_new)
        F.append_session_rounds(sessions_root, source, session_id, assigned)

        db.upsert_session(
            session_id=session_id, source=source, created_at=created_at,
            synced_at=now_iso, metadata=metadata, tags=[], round_count=len(assigned),
        )
        db.upsert_rounds(session_id, assigned)

        # LanceDB session text
        vectors.add_session(session_id, _rounds_to_session_text(assigned))

        events.emit(session_id, "imported", {
            "source": source, "round_count": len(assigned),
        })

        return {
            "status": "ok", "session_id": session_id, "action": "imported",
            "round_count": len(assigned), "added_count": len(assigned),
            "overwrite_skipped": [],
        }

    # Append path — existing session, sha256 changed
    if existing["source"] != source:
        raise SessionServiceError(f"source mismatch: existing={existing['source']!r}, new={source!r}")

    existing_rounds = db.list_rounds(session_id)
    by_round_id = {r["round_id"]: r for r in existing_rounds}
    next_idx = db.max_round_idx(session_id) + 1

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
            new_key = _round_key(r)
            if old_key == new_key:
                continue
            overwrite_skipped.append(old["idx"])
            continue
        rec = {
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
        }
        appended.append(rec)
        next_idx += 1

    total_count = existing["round_count"] + len(appended)

    if appended:
        F.append_session_rounds(sessions_root, source, session_id, appended)
        db.upsert_rounds(session_id, appended)
        db.update_session_round_count(session_id, total_count, now_iso)
        # Refresh session FTS text: aggregate over all rounds (old + new)
        all_rounds = db.list_rounds(session_id)
        vectors.add_session(session_id, _rounds_to_session_text(all_rounds))

    # Update meta.json (round_count, synced_at, last_sha256)
    meta_existing = F.read_session_meta(sessions_root, source, session_id) or {}
    meta_existing.update({"round_count": total_count, "synced_at": now_iso})
    if sha256:
        meta_existing["last_sha256"] = sha256
    F.write_session_meta(sessions_root, source, session_id, meta_existing)

    if appended and not overwrite_skipped:
        action = "appended"
        events.emit(session_id, "rounds_appended", {
            "from_index": appended[0]["idx"],
            "to_index": appended[-1]["idx"],
            "added_count": len(appended),
        })
    elif appended and overwrite_skipped:
        action = "partial_append"
        events.emit(session_id, "rounds_appended", {
            "from_index": appended[0]["idx"],
            "to_index": appended[-1]["idx"],
            "added_count": len(appended),
        })
        events.emit(session_id, "rounds_overwrite_skipped", {"indexes": overwrite_skipped})
    elif overwrite_skipped:
        action = "partial_append"  # still partial-like; no appends though
        events.emit(session_id, "rounds_overwrite_skipped", {"indexes": overwrite_skipped})
    else:
        # Nothing to do (all rounds already present & unchanged) but sha256 differed —
        # record the new sha256 as seen; no event.
        action = "skipped"

    return {
        "status": "ok", "session_id": session_id, "action": action,
        "round_count": total_count, "added_count": len(appended),
        "overwrite_skipped": overwrite_skipped,
    }

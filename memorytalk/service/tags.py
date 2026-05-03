"""TagService — kv-shaped management tags on session/card subjects.

Tag operations are structurally orthogonal to memory.talk's core data
model: tags don't enter the embedding index, don't trigger rebuild,
and are never read by search/recall. They're a property of a subject
that humans/tools use to organize content.

Public API:
- ``add_tags(subject_id, raw_tags)`` — upsert; emits per-key
  ``tag_added`` (new key) or ``tag_updated`` (key already existed with
  a different value). Same-value re-add is a no-op (no event).
- ``remove_tags(subject_id, keys)`` — delete by key; emits ``tag_removed``
  for each key that actually existed. Missing keys are silently
  skipped.

Subject routing happens off the id prefix:
- ``sess_*`` → session subject
- ``card_*`` → card subject
- anything else → ``TagServiceError``

After every mutation the service also rewrites a ``tags.json`` file
next to the subject's other on-disk files (``meta.json`` for sessions,
``card.json`` for cards). SQLite is the source of truth; ``tags.json``
is a mirror for external file-level inspection / backup.
"""
from __future__ import annotations
import json

from memorytalk.provider.storage import Storage
from memorytalk.repository import SQLiteStore
from memorytalk.schemas import TagPair, TagsResponse
from memorytalk.service.events import EventWriter
from memorytalk.service.sessions import SessionNotFound
from memorytalk.util.ids import CARD_PREFIX, SESSION_PREFIX
from memorytalk.util.ttl import dt_to_iso, now_utc


class TagServiceError(ValueError):
    """400 — invalid input (bad key, bad subject prefix, empty list)."""


SESSIONS_DIR = "sessions"
CARDS_DIR = "cards"


def _bucket(raw_id: str, prefix: str) -> str:
    raw = raw_id[len(prefix):] if raw_id.startswith(prefix) else raw_id
    return (raw[:2] if len(raw) >= 2 else raw).lower()


def _parse_tag(raw: str) -> tuple[str, str]:
    """Split ``"key:value"`` on the first ``:``. Trim both sides. Reject
    empty key (``":foo"`` / ``":"`` / ``""``)."""
    if ":" in raw:
        key, _, value = raw.partition(":")
    else:
        key, value = raw, ""
    key = key.strip()
    value = value.strip()
    if not key:
        raise TagServiceError(f"tag key cannot be empty: {raw!r}")
    return key, value


class TagService:
    def __init__(
        self, *,
        db: SQLiteStore,
        storage: Storage,
        events: EventWriter,
    ):
        self.db = db
        self.storage = storage
        self.events = events

    # -------- public --------

    async def add_tags(self, subject_id: str, raw_tags: list[str]) -> TagsResponse:
        if not raw_tags:
            raise TagServiceError("tags must be non-empty")
        type_ = self._subject_type(subject_id)
        await self._require_subject(subject_id, type_)

        now_iso = dt_to_iso(now_utc())

        for raw in raw_tags:
            key, value = _parse_tag(raw)
            result = await self.db.tags.upsert_one(subject_id, type_, key, value, now_iso)
            action = result["action"]
            if action == "added":
                await self.events.emit(subject_id, "tag_added",
                                       {"key": key, "value": value}, at=now_iso)
            elif action == "updated":
                await self.events.emit(subject_id, "tag_updated", {
                    "key": key, "value": value, "prior_value": result["prior_value"],
                }, at=now_iso)
            # unchanged: no event, no file rewrite needed for this key

        await self._sync_tags_file(subject_id, type_)
        pairs = await self.db.tags.list_for_subject(subject_id)
        return TagsResponse(tags=[TagPair(**p) for p in pairs])

    async def remove_tags(self, subject_id: str, keys: list[str]) -> TagsResponse:
        if not keys:
            raise TagServiceError("keys must be non-empty")
        type_ = self._subject_type(subject_id)
        await self._require_subject(subject_id, type_)

        now_iso = dt_to_iso(now_utc())

        for key in keys:
            removed = await self.db.tags.delete_one(subject_id, key)
            if removed is not None:
                await self.events.emit(subject_id, "tag_removed", {
                    "key": removed["key"], "value": removed["value"],
                }, at=now_iso)

        await self._sync_tags_file(subject_id, type_)
        pairs = await self.db.tags.list_for_subject(subject_id)
        return TagsResponse(tags=[TagPair(**p) for p in pairs])

    # -------- internals --------

    @staticmethod
    def _subject_type(subject_id: str) -> str:
        if subject_id.startswith(SESSION_PREFIX):
            return "session"
        if subject_id.startswith(CARD_PREFIX):
            return "card"
        raise TagServiceError("subject_id must start with sess_ or card_")

    async def _require_subject(self, subject_id: str, type_: str) -> None:
        if type_ == "session":
            row = await self.db.sessions.get(subject_id)
            if row is None:
                raise SessionNotFound(f"session not found: {subject_id}")
        else:  # card
            row = await self.db.cards.get(subject_id)
            if row is None:
                raise SessionNotFound(f"card not found: {subject_id}")

    async def _sync_tags_file(self, subject_id: str, type_: str) -> None:
        pairs = await self.db.tags.list_for_subject(subject_id)
        body = {p["key"]: p["value"] for p in pairs}
        key = await self._tags_file_key(subject_id, type_)
        if not body:
            # Empty tags → don't keep an empty file lying around.
            await self.storage.delete(key)
            return
        await self.storage.write_text(
            key, json.dumps(body, ensure_ascii=False, indent=2),
        )

    async def _tags_file_key(self, subject_id: str, type_: str) -> str:
        """Compute the on-disk path for ``tags.json``. session lives under
        ``sessions/{source}/{bucket}/{sid}/tags.json``; card lives under
        ``cards/{bucket}/{cid}/tags.json``."""
        if type_ == "session":
            session = await self.db.sessions.get(subject_id)
            source = session["source"] if session else "unknown"
            return f"{SESSIONS_DIR}/{source}/{_bucket(subject_id, SESSION_PREFIX)}/{subject_id}/tags.json"
        return f"{CARDS_DIR}/{_bucket(subject_id, CARD_PREFIX)}/{subject_id}/tags.json"

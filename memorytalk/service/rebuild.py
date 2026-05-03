"""Rebuild service — async reconstruct SQLite + LanceDB from file-layer truth.

All file IO routes through the per-domain Stores (which own Storage). The
service is provider-agnostic: same code path works whether the underlying
Storage is local FS or anything else implementing the protocol.
"""
from __future__ import annotations
import json

from memorytalk.config import Config
from memorytalk.provider.embedding import Embedder
from memorytalk.provider.lancedb import LanceStore
from memorytalk.provider.storage import Storage
from memorytalk.repository import SQLiteStore
from memorytalk.schemas import RebuildResponse
from memorytalk.util.ids import CARD_PREFIX, SESSION_PREFIX
from memorytalk.util.ttl import dt_to_iso, now_utc


def _bucket(raw_id: str, prefix: str) -> str:
    raw = raw_id[len(prefix):] if raw_id.startswith(prefix) else raw_id
    return (raw[:2] if len(raw) >= 2 else raw).lower()


async def _read_tags_json(storage: Storage, key: str) -> list[tuple[str, str]]:
    """Load tags.json from storage; return [(key, value), ...] preserving
    insertion order. Missing or malformed file → empty list."""
    text = await storage.read_text(key)
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    return [(str(k), str(v) if v is not None else "") for k, v in data.items()]


def _rounds_to_text(rounds: list[dict]) -> str:
    parts: list[str] = []
    for r in rounds:
        for b in r.get("content") or []:
            t = b.get("type")
            if t in ("text", "code"):
                parts.append(b.get("text") or "")
            elif t == "thinking":
                parts.append(b.get("thinking") or "")
    return "\n".join(p for p in parts if p)


def _card_emb_text(card: dict) -> str:
    rounds_text = "\n".join(r.get("text") or "" for r in (card.get("rounds") or []))
    summary = card.get("summary") or ""
    return f"{summary}\n{rounds_text}" if rounds_text else summary


class RebuildService:
    def __init__(
        self, *,
        config: Config,
        db: SQLiteStore,
        vectors: LanceStore,
        embedder: Embedder,
    ):
        self.config = config
        self.db = db
        self.vectors = vectors
        self.embedder = embedder

    async def rebuild(self) -> RebuildResponse:
        errors_count = 0
        now_iso = dt_to_iso(now_utc())

        await self.db.clear_all()
        await self.vectors.drop_cards()
        await self.vectors.drop_sessions()

        sessions_count = 0
        for source, session_id in await self.db.sessions.iter_keys():
            try:
                meta = await self.db.sessions.read_meta(source, session_id)
            except Exception:
                errors_count += 1
                continue
            if meta is None:
                continue

            try:
                rounds_from_file = await self.db.sessions.read_rounds_file(source, session_id)
            except Exception:
                errors_count += 1
                rounds_from_file = []

            await self.db.sessions.upsert(
                session_id=session_id, source=source,
                created_at=meta.get("created_at") or "",
                synced_at=meta.get("synced_at") or "",
                metadata=meta.get("metadata") or {},
                round_count=meta.get("round_count") or len(rounds_from_file),
            )
            if rounds_from_file:
                await self.db.sessions.upsert_rounds(session_id, rounds_from_file)
                await self.vectors.add_session(session_id, _rounds_to_text(rounds_from_file))

            tags_key = f"sessions/{source}/{_bucket(session_id, SESSION_PREFIX)}/{session_id}/tags.json"
            tag_pairs = await _read_tags_json(self.db.storage, tags_key)
            if tag_pairs:
                await self.db.tags.upsert_many(session_id, "session", tag_pairs, now_iso)

            sessions_count += 1

        cards_count = 0
        async for card in self.db.cards.iter_docs():
            card_id = card.get("card_id") or ""
            try:
                await self.db.cards.insert(
                    card_id=card_id,
                    summary=card.get("summary") or "",
                    rounds=card.get("rounds") or [],
                    created_at=card.get("created_at") or "",
                    expires_at=card.get("expires_at") or "",
                )
            except Exception:
                errors_count += 1
                continue
            emb_text = _card_emb_text(card)
            vector = await self.embedder.embed_one(emb_text)
            await self.vectors.add_card(card_id, emb_text, vector)

            if card_id:
                tags_key = f"cards/{_bucket(card_id, CARD_PREFIX)}/{card_id}/tags.json"
                tag_pairs = await _read_tags_json(self.db.storage, tags_key)
                if tag_pairs:
                    await self.db.tags.upsert_many(card_id, "card", tag_pairs, now_iso)

            cards_count += 1

        async for link in self.db.links.iter_docs():
            try:
                await self.db.links.insert(
                    link_id=link["link_id"],
                    source_id=link["source_id"], source_type=link["source_type"],
                    target_id=link["target_id"], target_type=link["target_type"],
                    comment=link.get("comment"),
                    expires_at=link.get("expires_at"),
                    created_at=link.get("created_at") or "",
                )
            except Exception:
                errors_count += 1

        searches_replayed, replay_errors = await self.db.search_log.replay_files()
        errors_count += replay_errors

        await self.vectors.ensure_fts_index("cards", replace=True)
        await self.vectors.ensure_fts_index("sessions", replace=True)

        await self.db.search_log.apply_retention(
            self.config.settings.search.search_log_retention_days
        )

        return RebuildResponse(
            status="ok",
            sessions=sessions_count,
            cards=cards_count,
            searches_replayed=searches_replayed,
            errors_count=errors_count,
        )

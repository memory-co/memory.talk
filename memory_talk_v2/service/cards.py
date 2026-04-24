"""Card service — create (write), view / log (read). All async."""
from __future__ import annotations
from typing import Any

from memory_talk_v2.config import Config
from memory_talk_v2.provider.embedding import Embedder
from memory_talk_v2.util.ids import (
    CARD_PREFIX, SESSION_PREFIX,
    new_card_id, new_link_id,
)
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.service.links import link_to_ref, refresh_active_user_links
from memory_talk_v2.util.ttl import (
    current_ttl, dt_to_iso, initial_expires_at, now_utc, refresh,
)
from memory_talk_v2.provider import files as F
from memory_talk_v2.provider.lancedb import LanceStore
from memory_talk_v2.repository import SQLiteStore


class CardServiceError(ValueError):
    """400 — validation."""


class CardConflictError(CardServiceError):
    """409 — card_id already exists."""


class CardNotFound(CardServiceError):
    """404 — card id well-formed but missing."""


def parse_indexes(expr: str) -> list[int]:
    if not expr or not expr.strip():
        raise CardServiceError("empty indexes")
    out: list[int] = []
    for part in expr.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                ai, bi = int(a), int(b)
            except ValueError:
                raise CardServiceError(f"bad range: {part!r}")
            if ai > bi:
                raise CardServiceError(f"range {part!r} is not ascending")
            out.extend(range(ai, bi + 1))
        else:
            try:
                out.append(int(part))
            except ValueError:
                raise CardServiceError(f"bad index: {part!r}")
    if not out:
        raise CardServiceError("no indexes produced")
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            raise CardServiceError("indexes must be monotonically increasing")
    return out


def compact_indexes(indexes: list[int]) -> str:
    if not indexes:
        return ""
    parts: list[str] = []
    run_start = prev = indexes[0]
    for n in indexes[1:]:
        if n == prev + 1:
            prev = n
            continue
        parts.append(f"{run_start}-{prev}" if run_start != prev else str(run_start))
        run_start = prev = n
    parts.append(f"{run_start}-{prev}" if run_start != prev else str(run_start))
    return ",".join(parts)


def _round_text_and_thinking(content: list[dict]) -> tuple[str, str | None]:
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for b in content or []:
        t = b.get("type")
        if t in ("text", "code"):
            text_parts.append(b.get("text") or "")
        elif t == "thinking":
            thinking_parts.append(b.get("thinking") or "")
    text = "\n".join(p for p in text_parts if p)
    thinking = "\n".join(p for p in thinking_parts if p) or None
    return text, thinking


class CardService:
    def __init__(
        self, *,
        config: Config,
        db: SQLiteStore,
        vectors: LanceStore,
        embedder: Embedder,
        events: EventWriter,
    ):
        self.config = config
        self.db = db
        self.vectors = vectors
        self.embedder = embedder
        self.events = events

    # -------- write --------

    async def create(self, payload: dict) -> dict:
        summary = (payload.get("summary") or "").strip()
        if not summary:
            raise CardServiceError("summary required")

        card_id = payload.get("card_id") or new_card_id()
        if not card_id.startswith(CARD_PREFIX):
            raise CardServiceError(f"invalid card_id prefix: {card_id!r}")
        if (await self.db.cards.get(card_id)) is not None:
            raise CardConflictError(f"card_id already exists: {card_id!r}")

        rounds_in = payload.get("rounds") or []

        expanded_rounds: list[dict] = []
        per_session_indexes: dict[str, list[int]] = {}
        per_session_order: list[str] = []

        for item in rounds_in:
            sid = item.get("session_id")
            if not sid or not sid.startswith(SESSION_PREFIX):
                raise CardServiceError("invalid session_id prefix")
            if (await self.db.sessions.get(sid)) is None:
                raise CardServiceError(f"session not found: {sid}")
            idxs = parse_indexes(item.get("indexes") or "")
            for idx in idxs:
                r = await self.db.sessions.get_round(sid, idx)
                if r is None:
                    raise CardServiceError(f"index {idx} out of range for session {sid}")
                text, thinking = _round_text_and_thinking(r["content"])
                expanded_rounds.append({
                    "role": r["role"] or "",
                    "text": text,
                    "thinking": thinking,
                    "session_id": sid,
                    "index": idx,
                })
            if sid not in per_session_indexes:
                per_session_indexes[sid] = []
                per_session_order.append(sid)
            per_session_indexes[sid].extend(idxs)

        now = now_utc()
        created_at = dt_to_iso(now)
        expires_at = initial_expires_at(self.config.settings.ttl.card.initial, now=now)

        card_doc = {
            "card_id": card_id, "summary": summary, "rounds": expanded_rounds,
            "created_at": created_at, "expires_at": expires_at,
        }

        await F.write_card(self.config.cards_dir, card_doc)
        await self.db.cards.insert(card_id, summary, expanded_rounds, created_at, expires_at)

        default_links: list[dict] = []
        for sid in per_session_order:
            link_id = new_link_id()
            link_doc = {
                "link_id": link_id, "source_id": card_id, "source_type": "card",
                "target_id": sid, "target_type": "session",
                "comment": None, "expires_at": None, "created_at": created_at,
            }
            await F.write_link(self.config.links_dir, link_doc)
            await self.db.links.insert(
                link_id=link_id, source_id=card_id, source_type="card",
                target_id=sid, target_type="session", comment=None,
                expires_at=None, created_at=created_at,
            )
            default_links.append({"link_id": link_id, "target_id": sid})

        rounds_text = "\n".join(r["text"] for r in expanded_rounds if r["text"])
        emb_text = summary if not rounds_text else f"{summary}\n{rounds_text}"
        vector = await self.embedder.embed_one(emb_text)
        await self.vectors.add_card(card_id, emb_text, vector)

        from_search_id = payload.get("from_search_id")
        rounds_echo = [
            {"session_id": sid, "indexes": compact_indexes(sorted(set(per_session_indexes[sid])))}
            for sid in per_session_order
        ]
        created_detail: dict[str, Any] = {
            "summary": summary, "rounds": rounds_echo,
            "default_links": default_links,
            "ttl_initial": self.config.settings.ttl.card.initial,
        }
        if from_search_id:
            created_detail["from_search_id"] = from_search_id
        await self.events.emit(card_id, "created", created_detail, at=created_at)

        for sid in per_session_order:
            dl = next((d for d in default_links if d["target_id"] == sid), None)
            await self.events.emit(sid, "card_extracted", {
                "card_id": card_id,
                "indexes": compact_indexes(sorted(set(per_session_indexes[sid]))),
                "default_link_id": dl["link_id"] if dl else None,
            }, at=created_at)

        return {"status": "ok", "card_id": card_id}

    # -------- reads --------

    async def view(self, card_id: str) -> dict:
        if not card_id.startswith(CARD_PREFIX):
            raise CardServiceError("invalid card_id prefix")
        card = await self.db.cards.get(card_id)
        if card is None:
            raise CardNotFound(f"card not found: {card_id}")

        now = now_utc()
        new_exp = refresh(
            card["expires_at"],
            self.config.settings.ttl.card.factor,
            self.config.settings.ttl.card.max,
            now=now,
        )
        if new_exp != card["expires_at"]:
            await self.db.cards.update_expires_at(card_id, new_exp)
            card["expires_at"] = new_exp

        links = await self.db.links.touching(card_id)
        await refresh_active_user_links(
            self.db, links,
            factor=self.config.settings.ttl.link.factor,
            max_seconds=self.config.settings.ttl.link.max,
            now=now,
        )

        return {
            "type": "card",
            "read_at": dt_to_iso(now),
            "card": {
                "card_id": card["card_id"], "summary": card["summary"],
                "rounds": card["rounds"], "created_at": card["created_at"],
                "ttl": current_ttl(card["expires_at"], now),
            },
            "links": [link_to_ref(l, card_id, now) for l in links],
        }

    async def log(self, card_id: str) -> dict:
        if not card_id.startswith(CARD_PREFIX):
            raise CardServiceError("invalid card_id prefix")
        if (await self.db.cards.get(card_id)) is None:
            raise CardNotFound(f"card not found: {card_id}")
        events = await F.read_card_events(self.config.cards_dir, card_id)
        events.sort(key=lambda e: e["at"])
        return {
            "type": "card",
            "card_id": card_id,
            "events": [{"at": e["at"], "kind": e["kind"], "detail": e["detail"]} for e in events],
        }

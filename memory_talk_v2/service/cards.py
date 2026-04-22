"""Cards creation service — validate, expand, default links, embed, emit events.

Design decisions (see spec §3.2):
- Validation-before-write: any invalid index/prefix/monotonicity → raise, nothing written
- Side-effect order: file → SQLite → vector → events
- Default links: one per distinct session_id, expires_at = NULL
- card_extracted event merged per session (indexes recompacted)
- from_search_id passed through into card.created event detail
"""
from __future__ import annotations
from typing import Any

from memory_talk_v2.config import Config
from memory_talk_v2.embedding import Embedder
from memory_talk_v2.ids import (
    CARD_PREFIX, SESSION_PREFIX,
    new_card_id, new_link_id, prefix_session_id,
)
from memory_talk_v2.service.events import EventWriter
from memory_talk_v2.service.ttl import dt_to_iso, initial_expires_at, now_utc
from memory_talk_v2.storage import files as F
from memory_talk_v2.storage.lancedb import LanceStore
from memory_talk_v2.storage.sqlite import SQLiteStore


class CardServiceError(ValueError):
    """Raised by the cards service; mapped to HTTP 400/409."""


class CardConflictError(CardServiceError):
    """Raised when card_id already exists (→ HTTP 409)."""


def parse_indexes(expr: str) -> list[int]:
    """Parse `"11-15"` or `"3,7,12"` into a list of ints. Strictly monotonic.

    Raises CardServiceError on parse failure or non-monotonic output.
    """
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
    """Opposite of parse_indexes: compact sorted ints into `"11-15,20,22"` form."""
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
        if t == "text" or t == "code":
            text_parts.append(b.get("text") or "")
        elif t == "thinking":
            thinking_parts.append(b.get("thinking") or "")
    text = "\n".join(p for p in text_parts if p)
    thinking = "\n".join(p for p in thinking_parts if p) or None
    return text, thinking


def create_card(
    payload: dict,
    *,
    config: Config,
    db: SQLiteStore,
    vectors: LanceStore,
    embedder: Embedder,
    events: EventWriter,
) -> dict:
    summary = (payload.get("summary") or "").strip()
    if not summary:
        raise CardServiceError("summary required")

    card_id = payload.get("card_id") or new_card_id()
    if not card_id.startswith(CARD_PREFIX):
        raise CardServiceError(f"invalid card_id prefix: {card_id!r}")
    if db.get_card(card_id) is not None:
        raise CardConflictError(f"card_id already exists: {card_id!r}")

    rounds_in = payload.get("rounds") or []

    # Validate all session_ids, ranges, and monotonicity BEFORE any side effect.
    expanded_rounds: list[dict] = []
    per_session_indexes: dict[str, list[int]] = {}  # session_id → ordered indexes used
    per_session_order: list[str] = []  # preserves first-appearance order

    for item in rounds_in:
        sid = item.get("session_id")
        if not sid or not sid.startswith(SESSION_PREFIX):
            raise CardServiceError("invalid session_id prefix")
        session_row = db.get_session(sid)
        if session_row is None:
            raise CardServiceError(f"session not found: {sid}")
        idxs = parse_indexes(item.get("indexes") or "")
        # range check per session
        for idx in idxs:
            r = db.get_round(sid, idx)
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
    expires_at = initial_expires_at(config.settings.ttl.card.initial, now=now)

    card_doc = {
        "card_id": card_id,
        "summary": summary,
        "rounds": expanded_rounds,
        "created_at": created_at,
        "expires_at": expires_at,
    }

    # File → SQLite → vectors → events
    F.write_card(config.cards_dir, card_doc)
    db.insert_card(card_id, summary, expanded_rounds, created_at, expires_at)

    # Default links (one per distinct session_id)
    default_links: list[dict] = []
    for sid in per_session_order:
        link_id = new_link_id()
        link_doc = {
            "link_id": link_id,
            "source_id": card_id,
            "source_type": "card",
            "target_id": sid,
            "target_type": "session",
            "comment": None,
            "expires_at": None,
            "created_at": created_at,
        }
        F.write_link(config.links_dir, link_doc)
        db.insert_link(
            link_id=link_id, source_id=card_id, source_type="card",
            target_id=sid, target_type="session", comment=None,
            expires_at=None, created_at=created_at,
        )
        default_links.append({"link_id": link_id, "target_id": sid})

    # Vector embedding
    rounds_text = "\n".join(r["text"] for r in expanded_rounds if r["text"])
    emb_text = summary if not rounds_text else f"{summary}\n{rounds_text}"
    vector = embedder.embed_one(emb_text)
    vectors.add_card(card_id, emb_text, vector)

    # Events: card.created, then session.card_extracted per session
    from_search_id = payload.get("from_search_id")
    rounds_echo = [
        {"session_id": sid, "indexes": compact_indexes(sorted(set(per_session_indexes[sid])))}
        for sid in per_session_order
    ]
    created_detail = {
        "summary": summary,
        "rounds": rounds_echo,
        "default_links": default_links,
        "ttl_initial": config.settings.ttl.card.initial,
    }
    if from_search_id:
        created_detail["from_search_id"] = from_search_id
    events.emit(card_id, "created", created_detail, at=created_at)

    for sid in per_session_order:
        dl = next((d for d in default_links if d["target_id"] == sid), None)
        events.emit(sid, "card_extracted", {
            "card_id": card_id,
            "indexes": compact_indexes(sorted(set(per_session_indexes[sid]))),
            "default_link_id": dl["link_id"] if dl else None,
        }, at=created_at)

    return {"status": "ok", "card_id": card_id}

"""Rebuild service — reconstruct SQLite + LanceDB from file-layer truth.

File layer (jsonl + single-object json) is the source of truth. Object
TTLs (expires_at) come from the files unchanged — rebuild does NOT reset
timers. Logs are replayed in lex (= date) order.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

from memory_talk_v2.config import Config
from memory_talk_v2.embedding import Embedder
from memory_talk_v2.storage import files as F
from memory_talk_v2.storage.lancedb import LanceStore
from memory_talk_v2.storage.sqlite import SQLiteStore


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


def _apply_retention(config: Config) -> None:
    days = config.settings.search.search_log_retention_days
    if days <= 0:
        return
    cutoff = time.time() - days * 86400
    for p in list(config.search_log_dir.glob("*.jsonl")):
        if p.stat().st_mtime < cutoff:
            p.unlink()


def rebuild(
    *,
    config: Config,
    db: SQLiteStore,
    vectors: LanceStore,
    embedder: Embedder,
) -> dict:
    errors_count = 0

    # 1) Drop everything and recreate
    db.clear_all()
    vectors.drop_cards()
    vectors.drop_sessions()

    # 2) Sessions
    sessions_count = 0
    for sess_dir in F.iter_session_dirs(config.sessions_dir):
        meta_path = sess_dir / "meta.json"
        rounds_path = sess_dir / "rounds.jsonl"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors_count += 1
            continue
        session_id = meta.get("session_id") or sess_dir.name
        source = meta.get("source") or sess_dir.parent.parent.name
        rounds_from_file: list[dict] = []
        if rounds_path.exists():
            for line in rounds_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rounds_from_file.append(json.loads(line))
                except json.JSONDecodeError:
                    errors_count += 1

        db.upsert_session(
            session_id=session_id, source=source,
            created_at=meta.get("created_at") or "",
            synced_at=meta.get("synced_at") or "",
            metadata=meta.get("metadata") or {},
            tags=meta.get("tags") or [],
            round_count=meta.get("round_count") or len(rounds_from_file),
        )
        if rounds_from_file:
            db.upsert_rounds(session_id, rounds_from_file)
            vectors.add_session(session_id, _rounds_to_text(rounds_from_file))
        sessions_count += 1

    # 3) Cards
    cards_count = 0
    for card in F.iter_cards(config.cards_dir):
        try:
            db.insert_card(
                card_id=card["card_id"],
                summary=card.get("summary") or "",
                rounds=card.get("rounds") or [],
                created_at=card.get("created_at") or "",
                expires_at=card.get("expires_at") or "",
            )
        except Exception:
            errors_count += 1
            continue
        emb_text = _card_emb_text(card)
        vector = embedder.embed_one(emb_text)
        vectors.add_card(card["card_id"], emb_text, vector)
        cards_count += 1

    # 4) Links (preserves expires_at, null for defaults)
    for link in F.iter_links(config.links_dir):
        try:
            db.insert_link(
                link_id=link["link_id"],
                source_id=link["source_id"],
                source_type=link["source_type"],
                target_id=link["target_id"],
                target_type=link["target_type"],
                comment=link.get("comment"),
                expires_at=link.get("expires_at"),
                created_at=link.get("created_at") or "",
            )
        except Exception:
            errors_count += 1

    # 5) Replay search_log jsonl
    searches_replayed = 0
    if config.search_log_dir.exists():
        for jsonl in sorted(config.search_log_dir.glob("*.jsonl")):
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    db.insert_search_log(
                        search_id=rec["search_id"], query=rec.get("query") or "",
                        where_dsl=rec.get("where"), top_k=int(rec.get("top_k") or 0),
                        created_at=rec.get("created_at") or "",
                        response_json=json.dumps(rec, ensure_ascii=False),
                    )
                    searches_replayed += 1
                except Exception:
                    errors_count += 1

    # Event log needs no rebuild step: events live inside each object's own
    # events.jsonl under cards/ or sessions/. They never left.

    # 7) FTS index refresh
    vectors.ensure_fts_index("cards", replace=True)
    vectors.ensure_fts_index("sessions", replace=True)

    # 8) Retention (file-level)
    _apply_retention(config)

    return {
        "status": "ok",
        "sessions": sessions_count,
        "cards": cards_count,
        "searches_replayed": searches_replayed,
        "errors_count": errors_count,
    }

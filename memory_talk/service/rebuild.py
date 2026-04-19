"""Rebuild SQLite + LanceDB from file system."""
from __future__ import annotations
import shutil
import threading
from datetime import datetime
from memory_talk.config import Config
from memory_talk.embedding import get_embedder
from memory_talk.storage.files import SessionFiles, CardFiles
from memory_talk.storage.init_db import init_db
from memory_talk.storage.sqlite import SQLiteStore
from memory_talk.storage.lancedb import LanceStore
from memory_talk.service.ttl import initial_expires_at
from memory_talk.service.session_text import rounds_to_text

def rebuild_async(config: Config) -> None:
    t = threading.Thread(target=_rebuild, args=(config,), daemon=True)
    t.start()

def _rebuild(config: Config) -> dict:
    if config.db_path.exists():
        config.db_path.unlink()
    if config.vectors_dir.exists():
        shutil.rmtree(config.vectors_dir)
    config.vectors_dir.mkdir(parents=True, exist_ok=True)

    init_db(config.db_path)
    db = SQLiteStore(config.db_path)
    vectors = LanceStore(config.vectors_dir, dim=config.settings.embedding.dim)
    embedder = get_embedder(config)

    session_files = SessionFiles(config.sessions_dir)
    session_count = 0
    for meta in session_files.scan_all():
        db.save_session(
            session_id=meta["session_id"], source=meta["source"],
            metadata=meta.get("metadata", {}), tags=meta.get("tags", []),
            round_count=meta.get("round_count", 0),
            created_at=meta.get("created_at"), synced_at=meta.get("synced_at"),
        )
        rounds = session_files.read_rounds(meta["source"], meta["session_id"])
        vectors.add_session(meta["session_id"], rounds_to_text(rounds))
        session_count += 1

    card_files = CardFiles(config.cards_dir)
    card_count = 0
    link_count = 0
    for card_data in card_files.scan_all():
        card_id = card_data["card_id"]
        expires_at = initial_expires_at(config.settings.ttl.card)
        db.save_card(card_id, card_data["summary"], card_data.get("session_id"), expires_at, card_data.get("created_at", datetime.now().isoformat()))
        card_count += 1

        from ulid import ULID
        for lk in card_data.get("links", []):
            link_id = str(ULID()).lower()
            link_expires = initial_expires_at(config.settings.ttl.link)
            db.save_link(link_id=link_id, source_id=card_id, source_type="card",
                target_id=lk["id"], target_type=lk["type"], comment=lk.get("comment"),
                expires_at=link_expires, created_at=card_data.get("created_at", datetime.now().isoformat()))
            link_count += 1

        text = f"{card_data['summary']}\n" + "\n".join(r.get("text", "") for r in card_data.get("rounds", []))
        embedding = embedder.embed_one(text)
        vectors.add(card_id, text, embedding)

    # Build FTS indexes on both tables (requires at least one row each).
    if card_count:
        vectors.ensure_fts_index(LanceStore.CARDS, replace=True)
    if session_count:
        vectors.ensure_fts_index(LanceStore.SESSIONS, replace=True)

    return {"status": "ok", "sessions": session_count, "cards": card_count, "links": link_count}

def rebuild_sync(config: Config) -> dict:
    return _rebuild(config)

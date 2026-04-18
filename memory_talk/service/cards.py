"""Cards service — create, get, list."""
from __future__ import annotations
from datetime import datetime
from ulid import ULID
from memory_talk.config import Config
from memory_talk.embedding import get_embedder
from memory_talk.service.ttl import compute_ttl, initial_expires_at, refresh_expires_at
from memory_talk.storage.sqlite import SQLiteStore
from memory_talk.storage.lancedb import LanceStore
from memory_talk.storage.files import CardFiles

class CardsService:
    def __init__(self, config: Config):
        self.config = config
        self.db = SQLiteStore(config.db_path)
        self.vectors = LanceStore(config.vectors_dir, dim=config.settings.embedding.dim)
        self.files = CardFiles(config.cards_dir)
        self.embedder = get_embedder(config)

    def create(self, data: dict) -> dict:
        card_id = data.get("card_id") or str(ULID()).lower()
        now = datetime.now()
        expires_at = initial_expires_at(self.config.settings.ttl.card)
        card_data = {
            "card_id": card_id, "summary": data["summary"],
            "session_id": data.get("session_id"), "rounds": data.get("rounds", []),
            "links": data.get("links", []), "created_at": now.isoformat(),
        }
        self.files.save(card_id, card_data)
        self.db.save_card(card_id, data["summary"], data.get("session_id"), expires_at, now.isoformat())

        # Create links
        from memory_talk.service.links import LinksService
        links_svc = LinksService(self.config)
        for lk in data.get("links", []):
            links_svc.create({
                "source_id": card_id, "source_type": "card",
                "target_id": lk["id"], "target_type": lk["type"],
                "comment": lk.get("comment"),
            })

        # Embed
        text = f"{data['summary']}\n" + "\n".join(r.get("text", "") for r in data.get("rounds", []))
        embedding = self.embedder.embed_one(text)
        self.vectors.add(card_id, text, embedding)
        return {"status": "ok", "card_id": card_id}

    def get(self, card_id: str, link_id: str | None = None) -> dict | None:
        card_data = self.files.read(card_id)
        if not card_data:
            return None
        db_card = self.db.get_card(card_id)
        if db_card:
            card_data["ttl"] = compute_ttl(db_card["expires_at"])
        links = self.db.get_links(card_id)
        card_data["links"] = [
            {"link_id": lk["link_id"],
             "id": lk["target_id"] if lk["source_id"] == card_id else lk["source_id"],
             "type": lk["target_type"] if lk["source_id"] == card_id else lk["source_type"],
             "comment": lk.get("comment"), "ttl": compute_ttl(lk["expires_at"])}
            for lk in links if compute_ttl(lk["expires_at"]) > 0
        ]
        if link_id:
            for lk in links:
                if lk["link_id"] == link_id:
                    new_exp = refresh_expires_at(lk["expires_at"], self.config.settings.ttl.link)
                    self.db.refresh_link_ttl(link_id, new_exp)
                    break
        return card_data

    def list_cards(self, session_id: str | None = None) -> list[dict]:
        rows = self.db.list_cards(session_id=session_id)
        return [{"card_id": r["card_id"], "summary": r["summary"], "session_id": r["session_id"], "ttl": compute_ttl(r["expires_at"])} for r in rows]

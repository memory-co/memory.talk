"""Recall service — vector search with TTL refresh."""
from __future__ import annotations
from memory_talk.config import Config
from memory_talk.embedding import get_embedder
from memory_talk.service.ttl import compute_ttl, refresh_expires_at
from memory_talk.storage.sqlite import SQLiteStore
from memory_talk.storage.lancedb import LanceStore
from memory_talk.storage.files import CardFiles

class RecallService:
    def __init__(self, config: Config):
        self.config = config
        self.db = SQLiteStore(config.db_path)
        self.vectors = LanceStore(config.vectors_dir)
        self.files = CardFiles(config.cards_dir)
        self.embedder = get_embedder(config)

    def recall(self, query: str, top_k: int = 5) -> dict:
        embedding = self.embedder.embed_one(query)
        hits = self.vectors.search(embedding, top_k=top_k)
        results = []
        for hit in hits:
            card_id = hit["card_id"]
            db_card = self.db.get_card(card_id)
            if not db_card:
                continue
            ttl = compute_ttl(db_card["expires_at"])
            if ttl <= 0:
                continue
            new_exp = refresh_expires_at(db_card["expires_at"], self.config.settings.ttl.card)
            self.db.refresh_card_ttl(card_id, new_exp)
            links_raw = self.db.get_links(card_id)
            links = [{"link_id": lk["link_id"],
                      "id": lk["target_id"] if lk["source_id"] == card_id else lk["source_id"],
                      "type": lk["target_type"] if lk["source_id"] == card_id else lk["source_type"],
                      "comment": lk["comment"], "ttl": compute_ttl(lk["expires_at"])}
                     for lk in links_raw if compute_ttl(lk["expires_at"]) > 0]
            results.append({"card_id": card_id, "summary": db_card["summary"],
                           "session_id": db_card["session_id"], "ttl": compute_ttl(new_exp),
                           "distance": hit["distance"], "links": links})
        return {"query": query, "results": results, "count": len(results)}

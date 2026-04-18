"""Links service — create, list, delete."""
from __future__ import annotations
from datetime import datetime
from ulid import ULID
from memory_talk.config import Config
from memory_talk.service.ttl import compute_ttl, initial_expires_at
from memory_talk.storage.sqlite import SQLiteStore

class LinksService:
    def __init__(self, config: Config):
        self.config = config
        self.db = SQLiteStore(config.db_path)

    def create(self, data: dict) -> dict:
        link_id = str(ULID()).lower()
        now = datetime.now()
        expires_at = initial_expires_at(self.config.settings.ttl.link)
        self.db.save_link(link_id=link_id, source_id=data["source_id"], source_type=data["source_type"],
            target_id=data["target_id"], target_type=data["target_type"],
            comment=data.get("comment"), expires_at=expires_at, created_at=now.isoformat())
        return {"status": "ok", "link_id": link_id}

    def list_links(self, obj_id: str, type_filter: str | None = None) -> list[dict]:
        rows = self.db.get_links(obj_id, object_type=type_filter)
        return [{"link_id": r["link_id"], "source_id": r["source_id"], "source_type": r["source_type"],
                 "target_id": r["target_id"], "target_type": r["target_type"],
                 "comment": r["comment"], "ttl": compute_ttl(r["expires_at"])} for r in rows]

    def delete(self, link_id: str) -> dict:
        self.db.delete_link(link_id)
        return {"status": "ok"}

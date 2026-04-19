"""Sessions service — import, list, read, tag."""
from __future__ import annotations
from datetime import datetime
from memory_talk.config import Config
from memory_talk.models.session import Session
from memory_talk.storage.sqlite import SQLiteStore
from memory_talk.storage.files import SessionFiles
from memory_talk.storage.lancedb import LanceStore
from memory_talk.service.session_text import rounds_to_text

class SessionsService:
    def __init__(self, config: Config):
        self.db = SQLiteStore(config.db_path)
        self.files = SessionFiles(config.sessions_dir)
        self.vectors = LanceStore(config.vectors_dir, dim=config.settings.embedding.dim)

    def import_session(self, session: Session) -> dict:
        self.files.save(session)
        synced_at = session.synced_at.isoformat() if session.synced_at else datetime.now().isoformat()
        created_at = session.created_at.isoformat() if session.created_at else None
        self.db.save_session(
            session_id=session.session_id, source=session.source,
            metadata=session.metadata, tags=session.tags,
            round_count=len(session.rounds), created_at=created_at, synced_at=synced_at,
        )
        text = rounds_to_text(session.rounds)
        self.vectors.add_session(session.session_id, text)
        self.vectors.ensure_fts_index(LanceStore.SESSIONS)
        return {"status": "ok", "session_id": session.session_id, "rounds": len(session.rounds)}

    def list_sessions(self, source: str | None = None, tag: str | None = None) -> list[dict]:
        rows = self.db.list_sessions(source=source)
        if tag:
            rows = [r for r in rows if tag in r.get("tags", [])]
        return rows

    def get_session(self, session_id: str, start: int | None = None, end: int | None = None) -> list[dict]:
        meta = self.db.get_session(session_id)
        if not meta:
            return []
        rounds = self.files.read_rounds(meta["source"], session_id, start=start or 0, end=end)
        return [r.model_dump(mode="json") for r in rounds]

    def add_tags(self, session_id: str, tags: list[str]) -> None:
        self.db.add_tags(session_id, tags)
        self._sync_tags_to_file(session_id)

    def remove_tags(self, session_id: str, tags: list[str]) -> None:
        self.db.remove_tags(session_id, tags)
        self._sync_tags_to_file(session_id)

    def _sync_tags_to_file(self, session_id: str) -> None:
        session_meta = self.db.get_session(session_id)
        if not session_meta:
            return
        file_meta = self.files.read_meta(session_meta["source"], session_id)
        if not file_meta:
            return
        file_meta["tags"] = session_meta.get("tags", [])
        self.files.save_meta(session_meta["source"], session_id, file_meta)

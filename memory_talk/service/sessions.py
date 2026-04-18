"""Sessions service — import, list, read, tag."""
from __future__ import annotations
from datetime import datetime
from memory_talk.config import Config
from memory_talk.models.session import Session
from memory_talk.storage.sqlite import SQLiteStore
from memory_talk.storage.files import SessionFiles

class SessionsService:
    def __init__(self, config: Config):
        self.db = SQLiteStore(config.db_path)
        self.files = SessionFiles(config.sessions_dir)

    def import_session(self, session: Session) -> dict:
        self.files.save(session)
        synced_at = session.synced_at.isoformat() if session.synced_at else datetime.now().isoformat()
        self.db.save_session(
            session_id=session.session_id, source=session.source,
            metadata=session.metadata, tags=session.tags,
            round_count=len(session.rounds), synced_at=synced_at,
        )
        return {"status": "ok", "session_id": session.session_id, "rounds": len(session.rounds)}

    def list_sessions(self, source: str | None = None) -> list[dict]:
        return self.db.list_sessions(source=source)

    def get_session(self, session_id: str, start: int | None = None, end: int | None = None) -> list[dict]:
        meta = self.db.get_session(session_id)
        if not meta:
            return []
        rounds = self.files.read_rounds(meta["source"], session_id, start=start or 0, end=end)
        return [r.model_dump(mode="json") for r in rounds]

    def add_tags(self, session_id: str, tags: list[str]) -> None:
        self.db.add_tags(session_id, tags)

    def remove_tags(self, session_id: str, tags: list[str]) -> None:
        self.db.remove_tags(session_id, tags)

"""File-based storage for raw sessions (JSONL files)."""

from __future__ import annotations

import json
from pathlib import Path

from memory_talk.models import Round, Session


class SessionStore:
    """Read/write sessions as JSONL files under sessions/{source}/{hash}/."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _session_path(self, source: str, session_id: str) -> Path:
        bucket = session_id[:2]
        return self.base_path / source / bucket / f"{session_id}.jsonl"

    def save(self, session: Session) -> Path:
        path = self._session_path(session.source, session.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in session.rounds:
                f.write(r.model_dump_json() + "\n")
        return path

    def read(self, source: str, session_id: str) -> list[Round]:
        path = self._session_path(source, session_id)
        if not path.exists():
            return []
        rounds = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rounds.append(Round.model_validate_json(line))
        return rounds

    def read_range(self, source: str, session_id: str, start: int, end: int) -> list[Round]:
        all_rounds = self.read(source, session_id)
        return all_rounds[start:end]

    def exists(self, source: str, session_id: str) -> bool:
        return self._session_path(source, session_id).exists()

"""File-based storage for sessions (JSONL) and cards (JSON)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

from memory_talk.models.session import Round, Session


class SessionFiles:
    def __init__(self, base: Path):
        self.base = base

    def _path(self, source: str, session_id: str) -> Path:
        return self.base / source / session_id[:2] / f"{session_id}.jsonl"

    def save(self, session: Session) -> Path:
        p = self._path(session.source, session.session_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f:
            for r in session.rounds:
                f.write(r.model_dump_json() + "\n")
        return p

    def read_rounds(
        self,
        source: str,
        session_id: str,
        start: int = 0,
        end: Optional[int] = None,
    ) -> list[Round]:
        p = self._path(source, session_id)
        if not p.exists():
            return []
        lines = p.read_text().strip().splitlines()
        subset = lines[start:end]
        return [Round.model_validate_json(line) for line in subset]


class CardFiles:
    def __init__(self, base: Path):
        self.base = base

    def _path(self, card_id: str) -> Path:
        return self.base / card_id[:2] / f"{card_id}.json"

    def save(self, card_id: str, data: dict) -> Path:
        p = self._path(card_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, default=str))
        return p

    def read(self, card_id: str) -> dict | None:
        p = self._path(card_id)
        if not p.exists():
            return None
        return json.loads(p.read_text())

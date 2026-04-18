"""File-based storage for sessions (JSONL) and cards (JSON)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

from memory_talk.models.session import Round, Session


class SessionFiles:
    def __init__(self, base: Path):
        self.base = base

    def _dir(self, source: str, session_id: str) -> Path:
        return self.base / source / session_id[:2] / session_id

    def _rounds_path(self, source: str, session_id: str) -> Path:
        return self._dir(source, session_id) / "rounds.jsonl"

    def _meta_path(self, source: str, session_id: str) -> Path:
        return self._dir(source, session_id) / "meta.json"

    def save(self, session: Session) -> Path:
        d = self._dir(session.source, session.session_id)
        d.mkdir(parents=True, exist_ok=True)
        with (d / "rounds.jsonl").open("w") as f:
            for r in session.rounds:
                f.write(r.model_dump_json() + "\n")
        meta = {
            "session_id": session.session_id,
            "source": session.source,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "synced_at": session.synced_at.isoformat() if session.synced_at else None,
            "metadata": session.metadata,
            "tags": session.tags,
            "round_count": len(session.rounds),
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str))
        return d

    def save_meta(self, source: str, session_id: str, meta: dict) -> None:
        p = self._meta_path(source, session_id)
        p.write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str))

    def read_meta(self, source: str, session_id: str) -> dict | None:
        p = self._meta_path(source, session_id)
        if not p.exists():
            return None
        return json.loads(p.read_text())

    def read_rounds(self, source: str, session_id: str, start: int = 0, end: Optional[int] = None) -> list[Round]:
        p = self._rounds_path(source, session_id)
        if not p.exists():
            return []
        lines = p.read_text().strip().splitlines()
        subset = lines[start:end]
        return [Round.model_validate_json(line) for line in subset]

    def scan_all(self) -> list[dict]:
        """Scan all session directories and return their meta.json contents."""
        results = []
        if not self.base.exists():
            return results
        for source_dir in sorted(self.base.iterdir()):
            if not source_dir.is_dir():
                continue
            for hash_dir in sorted(source_dir.iterdir()):
                if not hash_dir.is_dir():
                    continue
                for session_dir in sorted(hash_dir.iterdir()):
                    if not session_dir.is_dir():
                        continue
                    meta_path = session_dir / "meta.json"
                    if meta_path.exists():
                        results.append(json.loads(meta_path.read_text()))
        return results


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

    def scan_all(self) -> list[dict]:
        """Scan all card JSON files."""
        results = []
        if not self.base.exists():
            return results
        for hash_dir in sorted(self.base.iterdir()):
            if not hash_dir.is_dir():
                continue
            for card_file in sorted(hash_dir.glob("*.json")):
                results.append(json.loads(card_file.read_text()))
        return results

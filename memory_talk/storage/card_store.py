"""File-based storage for Talk-Card JSON files."""

from __future__ import annotations

from pathlib import Path

from memory_talk.models import TalkCard


class CardStore:
    """Read/write cards as JSON files under cards/{hash}/."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _card_path(self, card_id: str) -> Path:
        bucket = card_id[:2]
        return self.base_path / bucket / f"{card_id}.json"

    def save(self, card: TalkCard) -> Path:
        path = self._card_path(card.card_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(card.model_dump_json(indent=2))
        return path

    def read(self, card_id: str) -> TalkCard | None:
        path = self._card_path(card_id)
        if not path.exists():
            return None
        return TalkCard.model_validate_json(path.read_text(encoding="utf-8"))

    def exists(self, card_id: str) -> bool:
        return self._card_path(card_id).exists()

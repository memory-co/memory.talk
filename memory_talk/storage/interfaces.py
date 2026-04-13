"""Abstract interfaces for storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from memory_talk.models import TalkCard, CardLink


class VectorStore(ABC):
    """Store and search card embeddings."""

    @abstractmethod
    def add_card(self, card_id: str, text: str, embedding: list[float], metadata: dict[str, Any] | None = None) -> None:
        ...

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def delete_cards(self, card_ids: list[str]) -> None:
        ...


class RelationStore(ABC):
    """Store card metadata, links, session tracking."""

    @abstractmethod
    def save_card(self, card: TalkCard) -> None:
        ...

    @abstractmethod
    def get_card(self, card_id: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def list_cards(self, session_id: str | None = None) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def save_link(self, link: CardLink) -> None:
        ...

    @abstractmethod
    def get_links(self, card_id: str, link_types: list[str] | None = None) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def save_session(self, session_id: str, source: str, metadata: dict[str, Any], round_count: int) -> None:
        ...

    @abstractmethod
    def list_sessions(self, unbuilt_only: bool = False) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def mark_session_built(self, session_id: str) -> None:
        ...

    @abstractmethod
    def log_ingest(self, source_path: str, session_id: str, file_hash: str) -> None:
        ...

    @abstractmethod
    def is_ingested(self, source_path: str, file_hash: str) -> bool:
        ...

"""Base adapter interface for CLI `sync`."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator


class BaseAdapter(ABC):
    """Adapter for a source platform (claude-code / codex / ...).

    `iter_sessions(root)` yields ingest payloads — dicts with the shape of
    POST /v2/sessions body, including a computed sha256 for content hashing.
    """

    source_name: str

    @abstractmethod
    def iter_sessions(self, root: Path | None = None) -> Iterator[dict]: ...


ADAPTERS: dict[str, type[BaseAdapter]] = {}


def register(cls: type[BaseAdapter]) -> type[BaseAdapter]:
    ADAPTERS[cls.source_name] = cls
    return cls


def get_adapter(name: str) -> BaseAdapter:
    cls = ADAPTERS.get(name)
    if not cls:
        raise ValueError(f"unknown adapter: {name}")
    return cls()

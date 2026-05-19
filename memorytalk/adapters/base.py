"""Base adapter interface — produces ingest payloads from local files.

Adapters are stateless: they convert filesystem state into the dict shape
that ``POST /v3/sessions`` accepts. The sync watcher / backfill loop is
responsible for choosing when to call them.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator


class BaseAdapter(ABC):
    source_name: str

    @abstractmethod
    def watch_roots(self) -> list[Path]:
        """Directories the sync watcher should observe for this adapter."""

    @abstractmethod
    def iter_sessions(self) -> Iterator[dict]:
        """Yield ingest payloads — one per discovered session file."""

    @abstractmethod
    def convert_file(self, path: Path) -> dict | None:
        """Convert a single platform session file to an ingest payload.

        Returns ``None`` if the file isn't a recognized session file
        (e.g. wrong extension, empty content). The watcher calls this on
        every file event after debounce.
        """


ADAPTERS: dict[str, type[BaseAdapter]] = {}


def register(cls: type[BaseAdapter]) -> type[BaseAdapter]:
    ADAPTERS[cls.source_name] = cls
    return cls


def get_adapter(name: str) -> BaseAdapter:
    cls = ADAPTERS.get(name)
    if not cls:
        raise ValueError(f"unknown adapter: {name}")
    return cls()

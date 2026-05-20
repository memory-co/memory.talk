"""Base adapter — declares "where conversations come from" without saying
"how sync drives them".

An adapter is the in-process port for one upstream platform (Claude Code
on disk, a Codex API, …). It exposes three things to ``SyncWatcher``:

  - ``watch_roots()``  — directories the watchdog should observe
                         (file-source-only; remote adapters return [])
  - ``list_sources()`` — yield every ``SourceProbe`` known right now,
                         used by the cold-scan / backfill loop
  - ``probe(source_id)``        — cheap inspection of one artifact
  - ``read_after(...)`` — pull rounds strictly after a cursor

Sync owns the cursor state (sha + last_round_id + line_offset) in its
own ``sync.db``. Adapters are stateless ports.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from memorytalk.schemas import ReadAfterResult, SourceProbe


class BaseAdapter(ABC):
    source_name: str

    @abstractmethod
    def watch_roots(self) -> list[Path]:
        """Filesystem directories the sync watchdog should observe.
        Return ``[]`` for remote / non-filesystem adapters."""

    @abstractmethod
    def list_sources(self) -> Iterator[SourceProbe]:
        """Enumerate every upstream artifact this adapter currently
        knows about. Yields one ``SourceProbe`` per session.

        Sync uses this on backfill to walk the entire upstream surface;
        watchdog events bypass it and call ``probe`` on a single id.
        """

    @abstractmethod
    def probe(self, source_id: str) -> SourceProbe | None:
        """Inspect a single source artifact by its adapter-side id.

        Returns ``None`` if the artifact no longer exists or isn't a
        recognized session. The watcher calls this after debouncing a
        file event."""

    @abstractmethod
    def read_after(
        self,
        source_id: str,
        after_round_id: str | None,
        hint_line_offset: int = 0,
    ) -> ReadAfterResult:
        """Read rounds strictly after ``after_round_id``.

        ``hint_line_offset`` is the sync-side cached cursor offset.
        Adapters that can validate it (e.g. by parsing the next record
        at that offset and confirming its round_id == after_round_id)
        SHOULD use it as a fast-seek hint; if validation fails they
        MUST fall back to scanning from the start.

        ``after_round_id=None`` means "read from the very beginning"
        — used on first ingest of a previously-unseen session.
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

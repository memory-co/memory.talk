"""Base adapter — declares "where conversations come from" without saying
"how sync drives them".

An adapter is the in-process port for one upstream platform-AT-location
(Claude Code on disk, Codex on disk, an Openclaw HTTP endpoint, …).
Note "AT-location": the same source TYPE (e.g. ``openclaw``) can be
instantiated against multiple locations (e.g. US + EU endpoints), each
counted as a separate sync target. ``settings.sync.endpoints[]`` lists
the active (source, location) pairs at boot.

Each instance exposes:

  - ``watch_roots()``  — directories the watchdog should observe
                         (file-source-only; remote adapters return [])
  - ``list_sources()`` — yield every ``SourceProbe`` known right now,
                         used by the cold-scan / backfill loop
  - ``probe(source_id)``        — cheap inspection of one artifact
  - ``read_after(...)`` — pull rounds strictly after a cursor

Sync owns the cursor state (sha + last_round_id + line_offset) in its
own ``sync.db``. Adapters are stateless ports.

## session_id format

To prevent collisions when the same upstream id (e.g. an openclaw
``01HX...`` ULID) appears at multiple endpoints, every adapter mints
session_ids as ``sess-<8-hex>-<last-segment>`` where:

  - ``8-hex`` = ``sha256(f"{source}#{location}")[:8]`` — deterministic
    per (source, location), gives each endpoint a stable namespace.
  - ``last-segment`` = the chunk after the final ``-`` in the upstream
    id (git-commit-shorthand style). For ``019e5791-ab3d-76b1-8bcc-
    e0f410415f83`` that's ``e0f410415f83``. Upstream ids with no
    ``-`` get used verbatim.

This is the ONLY session_id format the codebase recognizes after the
0.7.x rewrite. Older ``sess_<UUID>`` data is intentionally not
backward-compatible — users were instructed to wipe ``~/.memory.talk``
and re-sync.
"""
from __future__ import annotations
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterator

from memorytalk.schemas import ReadAfterResult, SourceProbe


class BaseAdapter(ABC):
    source_name: str
    # Subclass sets to give a sensible default in setup wizard / settings.
    # ``None`` means "no default" (e.g. HTTP-based adapters where the user
    # must always specify a URL).
    DEFAULT_LOCATION: str | None = None

    def __init__(self, location: str, label: str | None = None, **extra: Any):
        """``location`` is the adapter-specific URI string the user typed
        in settings (filesystem path / URL / …). ``label`` is the
        UI-friendly name; defaults to ``location`` when None. ``extra``
        is bucket for adapter-specific options (e.g. ``auth_key``)."""
        self.location = location
        self.label = label or location
        # Stash extras for subclass __init__ to consume; keeping this on
        # the base means uniformly-shaped logs / events for unknown
        # extra keys (we don't silently swallow them).
        self.extras = extra

    # ─── identity helpers (don't override; subclasses just use mint_session_id) ───

    @property
    def endpoint_id(self) -> str:
        """Stable ``"<source>#<location>"`` key. Used as the hash input
        for session_id minting and as the audit key in events / display."""
        return f"{self.source_name}#{self.location}"

    @property
    def loc_code(self) -> str:
        """8-char hex deterministically derived from ``endpoint_id``.
        Same (source, location) → same code across machines / restarts."""
        return hashlib.sha256(self.endpoint_id.encode()).hexdigest()[:8]

    def mint_session_id(self, upstream_id: str) -> str:
        """Produce the canonical session_id for an upstream session.

        Format: ``sess-<loc_code>-<last_segment>`` where ``last_segment``
        is whatever comes after the final ``-`` in ``upstream_id`` (or
        the whole id if there's no ``-``). Letting only the last
        segment through keeps ids short (~22 chars) while preserving
        enough entropy for human eyeballing.

        Within a single (source, location), upstream ids are assumed
        unique by the upstream platform. Across endpoints, the
        ``loc_code`` prefix prevents collision.
        """
        # ULIDs / UUIDs may have no leading prefix to strip; split on
        # the final ``-`` and take the tail. If the tail is empty
        # (e.g. id ends with ``-``), fall back to the whole id sans
        # trailing separators.
        if "-" in upstream_id:
            last = upstream_id.rsplit("-", 1)[1] or upstream_id.rstrip("-")
        else:
            last = upstream_id
        return f"sess-{self.loc_code}-{last}"

    # ─── adapter contract ───

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


def get_adapter(name: str, location: str | None = None, **extras: Any) -> BaseAdapter:
    cls = ADAPTERS.get(name)
    if not cls:
        raise ValueError(f"unknown adapter: {name}")
    loc = location or cls.DEFAULT_LOCATION
    if loc is None:
        raise ValueError(
            f"adapter {name!r} has no DEFAULT_LOCATION; supply one explicitly"
        )
    return cls(location=loc, **extras)

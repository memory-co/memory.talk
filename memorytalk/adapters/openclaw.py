"""Openclaw adapter — HTTP-backed session source. **STUB** as of 0.7.x.

Registered into ``ADAPTERS`` so ``settings.sync.endpoints`` validation
recognizes ``openclaw`` as a known source, but every actual operation
raises ``NotImplementedError``. Listing an openclaw endpoint will
boot the server but produce a clear error in ``sync status`` instead
of silently doing nothing.

When implementing for real:

1. Confirm the openclaw API contract (auth header, endpoint paths,
   pagination, ETag / cursor semantics).
2. Map openclaw round shape → ``RoundInput`` — likely an
   OpenAI Chat Completions / Responses style envelope, similar to
   codex; reuse classification logic if so.
3. Decide cursor strategy: per-session ETag (preferred) vs whole-list
   cursor. The ``sync_session_checkpoint`` schema already carries
   ``sha256`` + ``last_round_id`` per-session, so per-session works.
4. Handle network failures: per-session retry vs whole-endpoint skip.
   The SyncWatcher's per-source try/except already isolates a bad
   endpoint from poisoning the others; just make sure ``probe`` /
   ``list_sources`` raise rather than swallow.
5. Rate limiting: keep per-endpoint state in adapter instance, not
   global — multiple openclaw endpoints (US + EU) might have
   independent quotas.
6. The session_id minting (``BaseAdapter.mint_session_id``) needs the
   upstream id to be reasonably stable; if openclaw doesn't expose a
   stable id, synthesize one from URL + endpoint params and document
   the choice prominently.
"""
from __future__ import annotations
from pathlib import Path
from typing import Iterator

from memorytalk.adapters.base import BaseAdapter, register
from memorytalk.schemas import ReadAfterResult, SourceProbe


@register
class OpenclawAdapter(BaseAdapter):
    source_name = "openclaw"
    # No DEFAULT_LOCATION — openclaw endpoints have no sensible default
    # URL. Users must list each one explicitly in settings.sync.endpoints.
    DEFAULT_LOCATION = None

    def watch_roots(self) -> list[Path]:
        # HTTP-based — nothing on disk for the watchdog to observe.
        return []

    def list_sources(self) -> Iterator[SourceProbe]:
        raise NotImplementedError(
            "openclaw adapter is not implemented yet. "
            "Remove the openclaw endpoint from settings.sync.endpoints, "
            "or wait for a release that ships this adapter."
        )

    def probe(self, source_id: str) -> SourceProbe | None:
        raise NotImplementedError("openclaw adapter not implemented")

    def read_after(
        self,
        source_id: str,
        after_round_id: str | None,
        hint_line_offset: int = 0,
    ) -> ReadAfterResult:
        raise NotImplementedError("openclaw adapter not implemented")

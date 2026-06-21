"""SessionMarkFileStore -- the mark file canonical (marks/<mark>.yaml).

A mark's body is canonical on disk as YAML, alongside the session's rounds:

  sessions/<source>/<bucket>/<sid>/
    rounds.jsonl              <- round bodies (v3)
    marks/
      m1.yaml                 <- one mark, file name == mark id
      m2.yaml

Body (docs/structure/v4/session-mark.md):
  last_index    optimistic-lock baseline (session round index when marked)
  description   the annotation scenario (carried from the submission)
  created_at    ISO 8601
  rounds        [{index, comment?, issues?: [{issue, card_id, is_new, indexes}]}]
                -- one entry per walked round (from index 1, ≥90% coverage).
                A bare {index} (no comment/issues) records "read, nothing to
                note" but still counts toward coverage.

This is the source of truth; ``session_marks`` (metadata) and
``card_sessions`` (the mark->card edges, from each round's ``issues[]``) are
derived SQLite indexes. Append-only: a mark file is written once, never
mutated (clearing a session removes the whole ``marks/`` dir).

The on-disk path mirrors ``SessionStore`` exactly (same <source>/<bucket>
derivation) so a session's whole footprint stays in one directory.
"""
from __future__ import annotations

import yaml

from memorytalk.provider.storage import Storage


class SessionMarkFileStore:
    PREFIX = "sessions"

    def __init__(self, storage: Storage):
        self.storage = storage

    @staticmethod
    def _bucket(session_id: str) -> str:
        raw = session_id[len("sess_"):] if session_id.startswith("sess_") else session_id
        return (raw[:2] if len(raw) >= 2 else raw).lower()

    def _doc_key(self, source: str, session_id: str, mark: str) -> str:
        return (
            f"{self.PREFIX}/{source}/{self._bucket(session_id)}"
            f"/{session_id}/marks/{mark}.yaml"
        )

    def _marks_dir(self, source: str, session_id: str) -> str:
        return (
            f"{self.PREFIX}/{source}/{self._bucket(session_id)}"
            f"/{session_id}/marks"
        )

    async def write_doc(
        self, source: str, session_id: str, mark: str, body: dict,
    ) -> None:
        """Write ``marks/<mark>.yaml`` (``body`` = the YAML doc). Flat
        positional args mirror sibling file-canonical stores
        (``SessionStore.write_meta`` / ``PositionStore.write_doc``)."""
        await self.storage.write_text(
            self._doc_key(source, session_id, mark),
            yaml.safe_dump(body, allow_unicode=True, sort_keys=False),
        )

    async def read_doc(self, source: str, session_id: str, mark: str) -> dict | None:
        text = await self.storage.read_text(self._doc_key(source, session_id, mark))
        return yaml.safe_load(text) if text else None

    async def delete_all(self, source: str, session_id: str) -> None:
        """Remove the whole ``marks/`` directory for a session (every
        ``m<n>.yaml``). Missing dir is a no-op. The session's other files
        (rounds.jsonl / meta.json / events.jsonl) live one level up and are
        untouched."""
        await self.storage.delete_prefix(self._marks_dir(source, session_id))

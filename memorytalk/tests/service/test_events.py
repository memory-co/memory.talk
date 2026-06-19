"""events.jsonl emission — every lifecycle event we promise to write.

v3 doesn't expose ``log`` as a CLI command (unlike v2), but the
events.jsonl files still exist as the audit trail. These tests pin down
which events fire when — so a future log-reader command or post-mortem
debug session can rely on them.

Event types covered:

| Event              | Where                                                              |
|--------------------|--------------------------------------------------------------------|
| imported           | sessions/<source>/<bucket>/<sid>/events.jsonl                       |
| rounds_appended    | same — on re-ingest with new rounds                                 |
| card_extracted     | per-session events.jsonl (one per referenced session)              |
| created            | cards/<bucket>/<cid>/events.jsonl                                   |
| card_linked        | cards/<bucket>/<source_card_id>/events.jsonl (the *target*)        |
| reviewed           | cards/<bucket>/<cid>/events.jsonl                                   |
| read               | cards/<bucket>/<cid>/events.jsonl                                   |

``rounds_overwrite_skipped`` is gone — v3 is append-only at the round
level and no longer detects (let alone reports) attempts to overwrite
existing round content.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


# ────────── helpers ──────────

from memorytalk.repository.sessions import SessionStore


def _session_events(data_root: Path, session_id: str) -> list[dict]:
    bucket = SessionStore._bucket(session_id)
    path = data_root / "sessions" / "claude-code" / bucket / session_id / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


async def _ingest(client, sid: str = "evt-src",
                  rounds: list[dict] | None = None,
                  sha: str = "sha1") -> str:
    # ``sha`` is unused under the new cursor-based API but kept in the
    # signature so existing call sites don't all need updates.
    del sha
    rounds = rounds if rounds is not None else [
        {"round_id": f"r{i}", "role": "human" if i % 2 else "assistant",
         "content": [{"type": "text", "text": f"round {i}"}]}
        for i in range(1, 4)
    ]
    r = await ingest_session(client, sid, metadata={"cwd": "/work"}, rounds=rounds)
    r.raise_for_status()
    return r.json()["session_id"]


# ────────── session lifecycle ──────────

class TestSessionEvents:
    async def test_imported_on_first_ingest(self, client, data_root):
        sid = await _ingest(client)
        events = _session_events(data_root, sid)
        kinds = [e["event"] for e in events]
        assert "imported" in kinds
        imported = next(e for e in events if e["event"] == "imported")
        assert imported["round_count"] == 3
        assert imported["added"] == 3

    async def test_rounds_appended_on_extra_round(self, client, data_root):
        sid = await _ingest(client)
        await _ingest(client, sha="sha2", rounds=[
            {"round_id": f"r{i}", "role": "human" if i % 2 else "assistant",
             "content": [{"type": "text", "text": f"round {i}"}]}
            for i in range(1, 5)  # one extra
        ])
        kinds = [e["event"] for e in _session_events(data_root, sid)]
        assert "rounds_appended" in kinds



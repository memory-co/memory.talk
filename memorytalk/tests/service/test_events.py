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


def _card_events(data_root: Path, card_id: str) -> list[dict]:
    raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
    bucket = (raw[:2] if len(raw) >= 2 else raw).lower()
    path = data_root / "cards" / bucket / card_id / "events.jsonl"
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


# ────────── card lifecycle ──────────

class TestCardEvents:
    async def test_created_event(self, client, data_root):
        sid = await _ingest(client)
        r = await client.post("/v3/cards", json={
            "insight": "the claim",
            "rounds": [{"session_id": sid, "indexes": "1-2"}],
        })
        cid = r.json()["card_id"]
        events = _card_events(data_root, cid)
        kinds = [e["event"] for e in events]
        assert "created" in kinds
        created = next(e for e in events if e["event"] == "created")
        assert created["round_count"] == 2

    async def test_card_extracted_event_on_source_session(self, client, data_root):
        """Each *unique* source session referenced by ``rounds[]`` receives
        a single ``card_extracted`` event."""
        sid = await _ingest(client)
        r = await client.post("/v3/cards", json={
            "insight": "x", "rounds": [{"session_id": sid, "indexes": "1-2"}],
        })
        cid = r.json()["card_id"]
        events = _session_events(data_root, sid)
        extracted = [e for e in events if e["event"] == "card_extracted"]
        assert len(extracted) == 1
        assert extracted[0]["card_id"] == cid

    async def test_card_extracted_merges_same_session(self, client, data_root):
        """Gap fill: v2 had this — when `rounds[]` lists the same session
        multiple times (e.g. ``1-3`` + ``5-7`` from one session), only one
        `card_extracted` event fires, not one per slice."""
        sid = await _ingest(client, rounds=[
            {"round_id": f"r{i}", "role": "human",
             "content": [{"type": "text", "text": f"round {i}"}]}
            for i in range(1, 6)
        ], sha="sha_long")
        await client.post("/v3/cards", json={
            "insight": "spans two slices of same session",
            "rounds": [
                {"session_id": sid, "indexes": "1-2"},
                {"session_id": sid, "indexes": "4-5"},
            ],
        })
        events = _session_events(data_root, sid)
        extracted = [e for e in events if e["event"] == "card_extracted"]
        assert len(extracted) == 1, (
            "card_extracted must merge — one card from this session should "
            "fire exactly one event regardless of how many slices it pulls"
        )

    async def test_card_linked_event_on_source_card_target(self, client, data_root):
        """When card B is created with ``source_cards: [{card_id: A, relation: ...}]``,
        card A's events.jsonl gets a ``card_linked`` event."""
        sid = await _ingest(client)
        r_parent = await client.post("/v3/cards", json={
            "insight": "parent",
            "rounds": [{"session_id": sid, "indexes": "1"}],
        })
        parent = r_parent.json()["card_id"]
        r_child = await client.post("/v3/cards", json={
            "insight": "child supersedes parent",
            "rounds": [{"session_id": sid, "indexes": "2"}],
            "source_cards": [{"card_id": parent, "relation": "supersedes"}],
        })
        child = r_child.json()["card_id"]
        events = _card_events(data_root, parent)
        linked = [e for e in events if e["event"] == "card_linked"]
        assert len(linked) == 1
        assert linked[0]["from_card"] == child
        assert linked[0]["relation"] == "supersedes"

    async def test_reviewed_event(self, client, data_root):
        sid = await _ingest(client)
        r = await client.post("/v3/cards", json={
            "insight": "x", "rounds": [{"session_id": sid, "indexes": "1"}],
        })
        cid = r.json()["card_id"]
        await client.post("/v3/reviews", json={
            "card_id": cid, "session_id": sid, "indexes": "2", "score": 1,
        })
        events = _card_events(data_root, cid)
        reviewed = [e for e in events if e["event"] == "reviewed"]
        assert len(reviewed) == 1
        assert reviewed[0]["score"] == 1
        # The event carries indexes (not comment — comment is in reviews.jsonl).
        assert reviewed[0]["indexes"] == "2"
        assert "comment" not in reviewed[0]

    async def test_read_event(self, client, data_root):
        sid = await _ingest(client)
        r = await client.post("/v3/cards", json={
            "insight": "x", "rounds": [{"session_id": sid, "indexes": "1"}],
        })
        cid = r.json()["card_id"]
        await client.post("/v3/read", json={"id": cid})
        events = _card_events(data_root, cid)
        kinds = [e["event"] for e in events]
        assert "read" in kinds

"""Ingest semantics: imported / appended / skipped / partial_append + events."""
from __future__ import annotations


def _payload(session_id="platform-abc", source="claude-code", sha256="h1", rounds=None):
    return {
        "session_id": session_id,
        "source": source,
        "created_at": "2026-04-10T00:00:00Z",
        "metadata": {"project": "demo"},
        "sha256": sha256,
        "rounds": rounds or [],
    }


def _round(rid, text, role="human"):
    return {
        "round_id": rid, "parent_id": None, "timestamp": "2026-04-10T00:00:00Z",
        "speaker": "user" if role == "human" else "assistant", "role": role,
        "content": [{"type": "text", "text": text}], "is_sidechain": False, "cwd": None,
    }


def test_first_ingest_imports(services):
    payload = _payload(rounds=[_round("r1", "hello"), _round("r2", "world", "assistant")])
    result = services.sessions.ingest(payload)
    assert result["action"] == "imported"
    assert result["session_id"].startswith("sess_")
    assert result["round_count"] == 2
    assert result["added_count"] == 2

    s = services.db.get_session(result["session_id"])
    assert s["round_count"] == 2

    rounds = services.db.list_rounds(result["session_id"])
    assert [r["idx"] for r in rounds] == [1, 2]

    events = services.events_for(result["session_id"])
    assert [e["kind"] for e in events] == ["imported"]
    assert events[0]["detail"]["round_count"] == 2


def test_same_sha256_is_skipped(services):
    payload = _payload(rounds=[_round("r1", "hello")])
    services.sessions.ingest(payload)
    second = services.sessions.ingest(payload)
    assert second["action"] == "skipped"
    assert second["added_count"] == 0


def test_appended_adds_new_rounds(services):
    p1 = _payload(rounds=[_round("r1", "hello")])
    services.sessions.ingest(p1)
    p2 = _payload(sha256="h2", rounds=[_round("r1", "hello"), _round("r2", "world", "assistant")])
    result = services.sessions.ingest(p2)
    assert result["action"] == "appended"
    assert result["added_count"] == 1
    assert result["round_count"] == 2

    kinds = [e["kind"] for e in services.events_for(result["session_id"])]
    assert kinds == ["imported", "rounds_appended"]


def test_partial_append_with_overwrite_skip(services):
    p1 = _payload(rounds=[_round("r1", "hello"), _round("r2", "world", "assistant")])
    first = services.sessions.ingest(p1)

    p2 = _payload(sha256="h2", rounds=[
        _round("r1", "HELLO CHANGED"),           # overwrite
        _round("r2", "world", "assistant"),      # unchanged
        _round("r3", "new stuff"),               # new
    ])
    result = services.sessions.ingest(p2)

    assert result["action"] == "partial_append"
    assert result["added_count"] == 1
    assert result["overwrite_skipped"] == [1]
    assert result["round_count"] == 3

    rounds = services.db.list_rounds(first["session_id"])
    assert rounds[0]["content"][0]["text"] == "hello"
    assert [r["idx"] for r in rounds] == [1, 2, 3]

    kinds = [e["kind"] for e in services.events_for(result["session_id"])]
    assert kinds == ["imported", "rounds_appended", "rounds_overwrite_skipped"]

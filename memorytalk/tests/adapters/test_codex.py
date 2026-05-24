"""CodexAdapter — envelope parsing + per-line round_id determinism.

Covers the four classifications that produce rounds and the skip rules
that prevent double-counting messages already surfaced via
``event_msg``. Doesn't try to be a fixture for live codex output —
the format is shaped by hand from documented envelope types.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import pytest

from memorytalk.adapters.codex import CodexAdapter


def _env(typ: str, payload: dict, ts: str = "2026-05-20T00:00:00Z") -> dict:
    return {"timestamp": ts, "type": typ, "payload": payload}


def _write(path: Path, envelopes: list[dict]) -> None:
    path.write_text("".join(json.dumps(e) + "\n" for e in envelopes))


def _adapter(tmp_path: Path) -> CodexAdapter:
    return CodexAdapter(location=str(tmp_path))


# ────────── probe ──────────

def test_probe_extracts_session_id_from_session_meta(tmp_path):
    f = tmp_path / "2026/05/20/rollout-2026-05-20T00-00-00-deadbeef-cafe-1234-5678-abcdef012345.jsonl"
    f.parent.mkdir(parents=True)
    _write(f, [
        _env("session_meta", {"id": "session-uuid-from-meta", "cwd": "/work/proj"}),
        _env("event_msg", {"type": "user_message", "message": "hi"}),
    ])
    probe = _adapter(tmp_path).probe(str(f))
    assert probe is not None
    assert probe.session_id == "session-uuid-from-meta"
    assert probe.metadata.get("cwd") == "/work/proj"
    assert probe.sha256 == hashlib.sha256(f.read_bytes()).hexdigest()


def test_probe_falls_back_to_filename_uuid_when_meta_missing(tmp_path):
    """Truncated file (no session_meta envelope) — uuid comes from filename."""
    fname = "rollout-2026-05-20T00-00-00-deadbeef-cafe-1234-5678-abcdef012345.jsonl"
    f = tmp_path / "2026/05/20" / fname
    f.parent.mkdir(parents=True)
    _write(f, [_env("event_msg", {"type": "user_message", "message": "no meta"})])
    probe = _adapter(tmp_path).probe(str(f))
    assert probe is not None
    assert probe.session_id == "deadbeef-cafe-1234-5678-abcdef012345"


# ────────── read_after envelope classification ──────────

def test_read_after_keeps_user_and_agent_messages(tmp_path):
    f = tmp_path / "s.jsonl"
    _write(f, [
        _env("session_meta", {"id": "s1"}),  # skipped (not a round)
        _env("event_msg", {"type": "user_message", "message": "hello"}),
        _env("event_msg", {"type": "agent_message", "message": "hi back"}),
    ])
    rounds = _adapter(tmp_path).read_after(str(f), after_round_id=None).rounds
    assert [r.role for r in rounds] == ["human", "assistant"]
    assert rounds[0].content[0].text == "hello"
    assert rounds[1].content[0].text == "hi back"


def test_read_after_keeps_function_call_and_output(tmp_path):
    f = tmp_path / "s.jsonl"
    _write(f, [
        _env("response_item", {
            "type": "function_call",
            "name": "shell",
            "arguments": '{"cmd":"ls"}',
        }),
        _env("response_item", {
            "type": "function_call_output",
            "output": "file1\nfile2",
        }),
    ])
    rounds = _adapter(tmp_path).read_after(str(f), after_round_id=None).rounds
    assert [r.role for r in rounds] == ["assistant", "tool"]
    assert rounds[0].content[0].type == "tool_use"
    assert rounds[0].content[0].name == "shell"
    assert rounds[1].content[0].type == "tool_result"
    assert "file1" in rounds[1].content[0].text


def test_read_after_keeps_reasoning_with_encrypted_marker(tmp_path):
    f = tmp_path / "s.jsonl"
    _write(f, [
        _env("response_item", {
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "abc==",
        }),
    ])
    rounds = _adapter(tmp_path).read_after(str(f), after_round_id=None).rounds
    assert len(rounds) == 1
    assert rounds[0].content[0].type == "thinking"
    assert "encrypted" in rounds[0].content[0].thinking.lower()


def test_read_after_skips_telemetry_and_duplicate_wire_message(tmp_path):
    """response_item/message is the wire form of event_msg/user_message and
    event_msg/agent_message — keeping both would double the round count.
    Telemetry envelopes are also dropped."""
    f = tmp_path / "s.jsonl"
    _write(f, [
        _env("event_msg", {"type": "user_message", "message": "q"}),
        _env("response_item", {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "q"}],
        }),  # skip — duplicate of event_msg above
        _env("event_msg", {"type": "task_started"}),
        _env("event_msg", {"type": "task_complete"}),
        _env("event_msg", {"type": "token_count", "input": 10, "output": 5}),
        _env("event_msg", {"type": "agent_message", "message": "a"}),
        _env("response_item", {
            "type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": "a"}],
        }),  # skip — duplicate
    ])
    rounds = _adapter(tmp_path).read_after(str(f), after_round_id=None).rounds
    assert [r.role for r in rounds] == ["human", "assistant"]


# ────────── round_id determinism ──────────

def test_round_id_is_deterministic_per_line(tmp_path):
    """``mint_session_id`` aside — round_ids must be reproducible so
    ``after_round_id`` resumption works across process restarts."""
    f = tmp_path / "s.jsonl"
    _write(f, [
        _env("event_msg", {"type": "user_message", "message": "a"}),
        _env("event_msg", {"type": "agent_message", "message": "b"}),
    ])
    a = _adapter(tmp_path).read_after(str(f), after_round_id=None).rounds
    b = _adapter(tmp_path).read_after(str(f), after_round_id=None).rounds
    assert [r.round_id for r in a] == [r.round_id for r in b]


def test_read_after_resumes_from_round_id(tmp_path):
    f = tmp_path / "s.jsonl"
    _write(f, [
        _env("event_msg", {"type": "user_message", "message": "first"}),
        _env("event_msg", {"type": "agent_message", "message": "second"}),
        _env("event_msg", {"type": "user_message", "message": "third"}),
    ])
    ad = _adapter(tmp_path)
    all_rounds = ad.read_after(str(f), after_round_id=None).rounds
    # Resume after the second round → expect only "third".
    resumed = ad.read_after(str(f), after_round_id=all_rounds[1].round_id).rounds
    assert [b.text for b in (r.content[0] for r in resumed)] == ["third"]


# ────────── list_sources walks YYYY/MM/DD ──────────

def test_list_sources_finds_files_in_date_subdirs(tmp_path):
    for d in ["2026/05/19", "2026/05/20"]:
        sub = tmp_path / d
        sub.mkdir(parents=True)
        f = sub / f"rollout-2026-05-19T00-00-00-{d.replace('/', '-')}-aaaa-bbbb-cccc-dddddddddddd.jsonl"
        _write(f, [
            _env("session_meta", {"id": f"sid-{d}"}),
            _env("event_msg", {"type": "user_message", "message": "x"}),
        ])
    probes = list(_adapter(tmp_path).list_sources())
    sids = sorted(p.session_id for p in probes)
    assert len(sids) == 2
    assert all(s.startswith("sid-2026/05/") for s in sids)

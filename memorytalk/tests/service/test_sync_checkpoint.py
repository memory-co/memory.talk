"""SyncCheckpointStore (the per-source cursor for upstream state) and
the line-offset hint validation inside ClaudeCodeAdapter.read_after.
"""
from __future__ import annotations
import json

from memorytalk.repository.sync_checkpoint import SyncCheckpointStore


_LOC = "/home/u/.claude/projects"  # arbitrary; checkpoint PK now includes it


async def test_checkpoint_roundtrip(tmp_path):
    store = await SyncCheckpointStore.create(tmp_path / "sync.db")
    try:
        assert await store.get("claude-code", _LOC, "s1") is None
        await store.upsert(
            source="claude-code", location=_LOC, session_id="s1",
            sha256="aaa", last_round_id="r5", line_offset=42,
            updated_at="2026-05-20T00:00:00Z",
        )
        row = await store.get("claude-code", _LOC, "s1")
        assert row == {
            "sha256": "aaa", "last_round_id": "r5",
            "line_offset": 42, "updated_at": "2026-05-20T00:00:00Z",
        }
        assert await store.count() == 1

        # Same key updates in place
        await store.upsert(
            source="claude-code", location=_LOC, session_id="s1",
            sha256="bbb", last_round_id="r6", line_offset=50,
            updated_at="2026-05-20T01:00:00Z",
        )
        assert (await store.get("claude-code", _LOC, "s1"))["sha256"] == "bbb"
        assert await store.count() == 1
    finally:
        await store.close()


async def test_checkpoint_keyed_by_source_and_session(tmp_path):
    """(source, location, session_id) PK lets two adapters share a
    session_id without colliding — important for the multi-endpoint and
    future remote ingest paths."""
    store = await SyncCheckpointStore.create(tmp_path / "sync.db")
    try:
        await store.upsert(
            source="claude-code", location=_LOC, session_id="s1",
            sha256="a", last_round_id="r1", line_offset=1, updated_at="t1",
        )
        await store.upsert(
            source="codex", location="/home/u/.codex/sessions",
            session_id="s1", sha256="b", last_round_id="r2",
            line_offset=2, updated_at="t2",
        )
        cc = await store.get("claude-code", _LOC, "s1")
        cx = await store.get("codex", "/home/u/.codex/sessions", "s1")
        assert cc["sha256"] == "a" and cc["last_round_id"] == "r1"
        assert cx["sha256"] == "b" and cx["last_round_id"] == "r2"
        assert await store.count() == 2
    finally:
        await store.close()


async def test_checkpoint_keyed_by_location_too(tmp_path):
    """Two endpoints of the same source (e.g. US vs EU openclaw) must
    keep separate cursors for the same session_id."""
    store = await SyncCheckpointStore.create(tmp_path / "sync.db")
    try:
        await store.upsert(
            source="openclaw", location="https://us.openclaw.example",
            session_id="s1", sha256="us", last_round_id="rU",
            line_offset=10, updated_at="t1",
        )
        await store.upsert(
            source="openclaw", location="https://eu.openclaw.example",
            session_id="s1", sha256="eu", last_round_id="rE",
            line_offset=20, updated_at="t2",
        )
        us = await store.get("openclaw", "https://us.openclaw.example", "s1")
        eu = await store.get("openclaw", "https://eu.openclaw.example", "s1")
        assert us["sha256"] == "us" and us["last_round_id"] == "rU"
        assert eu["sha256"] == "eu" and eu["last_round_id"] == "rE"
        assert await store.count() == 2
    finally:
        await store.close()


def _claude_jsonl(rounds: list[tuple[str, str, str]]) -> str:
    """Build a minimal Claude Code-shaped .jsonl from (uuid, type, text)."""
    out = []
    for uuid, mtype, text in rounds:
        out.append(json.dumps({
            "type": mtype, "uuid": uuid, "parentUuid": None,
            "timestamp": "2026-05-20T00:00:00Z", "isSidechain": False,
            "cwd": "/work",
            "message": {"role": mtype, "content": [{"type": "text", "text": text}]},
        }))
    return "\n".join(out) + "\n"


def test_claude_read_after_hint_offset_valid_fast_paths(tmp_path):
    """When ``hint_line_offset`` correctly points at the line AFTER the
    expected round_id, adapter can fast-seek and skip the rest."""
    from memorytalk.adapters.claude_code import ClaudeCodeAdapter
    f = tmp_path / "sess.jsonl"
    f.write_text(_claude_jsonl([
        ("u1", "user", "first"),
        ("a1", "assistant", "second"),
        ("u2", "user", "third"),
        ("a2", "assistant", "fourth"),
    ]))
    adapter = ClaudeCodeAdapter(location=ClaudeCodeAdapter.DEFAULT_LOCATION)
    # hint = 2 → line at idx 1 is "a1"; we expect rounds after a1 → u2,a2
    result = adapter.read_after(str(f), after_round_id="a1", hint_line_offset=2)
    assert [r.round_id for r in result.rounds] == ["u2", "a2"]
    assert result.next_line_offset == 4


def test_claude_read_after_invalid_hint_falls_back_to_scan(tmp_path):
    """A wrong hint must NOT silently yield bogus rounds. The adapter
    re-scans from the top to locate the marker."""
    from memorytalk.adapters.claude_code import ClaudeCodeAdapter
    f = tmp_path / "sess.jsonl"
    f.write_text(_claude_jsonl([
        ("u1", "user", "first"),
        ("a1", "assistant", "second"),
        ("u2", "user", "third"),
    ]))
    adapter = ClaudeCodeAdapter(location=ClaudeCodeAdapter.DEFAULT_LOCATION)
    # hint claims line 1 carries "a1" but it actually carries "u1" →
    # adapter scans and finds a1 at line 2, yields u2 only.
    result = adapter.read_after(str(f), after_round_id="a1", hint_line_offset=1)
    assert [r.round_id for r in result.rounds] == ["u2"]


def test_claude_read_after_with_unknown_marker_yields_all(tmp_path):
    """If the marker isn't in the file at all (e.g., file was rewritten
    on the source side), the adapter behaves as if the cursor is None
    — yields everything. SyncWatcher's conflict path then kicks in via
    expected_prev_round_id mismatch in ingest."""
    from memorytalk.adapters.claude_code import ClaudeCodeAdapter
    f = tmp_path / "sess.jsonl"
    f.write_text(_claude_jsonl([
        ("u1", "user", "first"),
        ("a1", "assistant", "second"),
    ]))
    adapter = ClaudeCodeAdapter(location=ClaudeCodeAdapter.DEFAULT_LOCATION)
    result = adapter.read_after(str(f), after_round_id="ghost", hint_line_offset=99)
    assert [r.round_id for r in result.rounds] == ["u1", "a1"]


def test_claude_read_after_none_cursor_yields_everything(tmp_path):
    from memorytalk.adapters.claude_code import ClaudeCodeAdapter
    f = tmp_path / "sess.jsonl"
    f.write_text(_claude_jsonl([
        ("u1", "user", "first"),
        ("a1", "assistant", "second"),
    ]))
    adapter = ClaudeCodeAdapter(location=ClaudeCodeAdapter.DEFAULT_LOCATION)
    result = adapter.read_after(str(f), after_round_id=None, hint_line_offset=0)
    assert [r.round_id for r in result.rounds] == ["u1", "a1"]
    assert result.next_line_offset == 2

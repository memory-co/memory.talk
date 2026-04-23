"""Sync scenario: claude-code JSONL → ClaudeCodeAdapter → POST /v2/sessions.

Self-contained test case: the raw native-format JSONL under `platform/` and
the expected-outcome `expected.json` sit alongside this script. Adding
another scenario means creating a sibling directory under
`memory_talk_v2/tests/sync/` with its own `test.py` + data.
"""
from __future__ import annotations
import json
from pathlib import Path


HERE = Path(__file__).parent
PLATFORM = HERE / "platform"
EXPECTED = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))


def test_claude_code_sync(app_client):
    from memory_talk_v2.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter()
    actions = []
    for payload in adapter.iter_sessions(PLATFORM):
        r = app_client.post("/v2/sessions", json=payload)
        assert r.status_code == 200, r.text
        actions.append(r.json())

    assert len(actions) == 1, "fixture expects exactly one session"
    action = actions[0]
    assert action["action"] == "imported"
    assert action["session_id"] == EXPECTED["session_id"]
    assert action["round_count"] == EXPECTED["round_count"]

    view = app_client.post("/v2/view", json={"id": EXPECTED["session_id"]}).json()
    s = view["session"]
    assert s["source"] == EXPECTED["source"]
    assert s["metadata"].get("project") == EXPECTED["metadata_project"]
    assert s["tags"] == EXPECTED["tags"]

    first = s["rounds"][EXPECTED["first_round"]["index"] - 1]
    assert first["role"] == EXPECTED["first_round"]["role"]
    first_text = "".join((b.get("text") or "") for b in first["content"])
    assert EXPECTED["first_round"]["text_contains"] in first_text

    aw_e = EXPECTED["assistant_round_with_thinking"]
    aw = s["rounds"][aw_e["index"] - 1]
    assert aw["role"] == aw_e["role"]
    aw_text = "".join((b.get("text") or "") for b in aw["content"])
    assert aw_e["text_contains"] in aw_text
    has_thinking = any(b["type"] == "thinking" for b in aw["content"])
    assert has_thinking is aw_e["content_has_thinking_block"]

    log = app_client.post("/v2/log", json={"id": EXPECTED["session_id"]}).json()
    assert [e["kind"] for e in log["events"]] == EXPECTED["events_kinds"]

    # Idempotency: same bytes → skipped
    for payload in adapter.iter_sessions(PLATFORM):
        r = app_client.post("/v2/sessions", json=payload)
        assert r.json()["action"] == "skipped"

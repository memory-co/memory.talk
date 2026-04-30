"""recall — accepts any session_id, doesn't require existence in v2."""
from __future__ import annotations
import json


async def test_recall_for_unknown_session_no_corpus(cli_env):
    """No seeding at all — corpus empty, session_id never imported.
    recall must still succeed (cards bucket just returns nothing)."""
    result = cli_env.runner.invoke(cli_env.main, [
        "recall", "totally-fresh", "anything goes",
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["session_id"] == "sess_totally-fresh"
    assert out["round_count"] == 1
    assert out["recalled"] == []
    assert out["skipped_already_recalled"] == []


async def test_recall_already_prefixed_session_id(cli_env):
    """If caller passes sess_<id>, prefix_session_id is idempotent."""
    result = cli_env.runner.invoke(cli_env.main, [
        "recall", "sess_pre-prefixed", "test query",
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["session_id"] == "sess_pre-prefixed"
    assert not out["session_id"].startswith("sess_sess_")

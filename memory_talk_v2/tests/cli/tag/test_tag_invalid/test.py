"""`memory-talk tag {add,remove}` — error paths (wrong target type / missing session)."""
from __future__ import annotations
import json


async def _run_add(cli_env, object_id: str, *tags: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "tag", "add", object_id, *tags,
        "--data-root", str(cli_env.config.data_root),
    ])
    return result.exit_code, json.loads(result.stdout)


async def _run_remove(cli_env, object_id: str, *tags: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "tag", "remove", object_id, *tags,
        "--data-root", str(cli_env.config.data_root),
    ])
    return result.exit_code, json.loads(result.stdout)


async def test_tag_add_on_card_prefix_rejected(cli_env):
    exit_code, out = await _run_add(cli_env, "card_something", "decision")
    assert exit_code != 0
    # Tags only apply to sessions — card_ prefix → type mismatch
    assert "type mismatch" in str(out["error"]) or "session" in str(out["error"])


async def test_tag_add_on_unknown_session_returns_404(cli_env):
    exit_code, out = await _run_add(cli_env, "sess_does_not_exist", "decision")
    assert exit_code != 0
    assert "not found" in str(out["error"])


async def test_tag_remove_on_card_prefix_rejected(cli_env):
    exit_code, out = await _run_remove(cli_env, "card_xxx", "decision")
    assert exit_code != 0
    assert "type mismatch" in str(out["error"]) or "session" in str(out["error"])


async def test_tag_remove_on_unknown_session_returns_404(cli_env):
    exit_code, out = await _run_remove(cli_env, "sess_missing", "decision")
    assert exit_code != 0
    assert "not found" in str(out["error"])


async def test_tag_add_on_bad_prefix_rejected(cli_env):
    # No v2 prefix at all
    exit_code, out = await _run_add(cli_env, "plain-no-prefix", "decision")
    assert exit_code != 0
    assert "type mismatch" in str(out["error"]) or "session" in str(out["error"])

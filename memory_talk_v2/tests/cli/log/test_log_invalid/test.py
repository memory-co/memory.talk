"""`memory-talk log <id>` — error paths (bad prefix / object missing)."""
from __future__ import annotations
import json


async def _run(cli_env, object_id: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "log", object_id,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def test_log_bad_prefix_rejected(cli_env):
    exit_code, out = await _run(cli_env, "foo_bar_12345")
    assert exit_code != 0
    assert "invalid id prefix" in str(out["error"])


async def test_log_unprefixed_id_rejected(cli_env):
    exit_code, out = await _run(cli_env, "plain-no-prefix")
    assert exit_code != 0
    assert "invalid id prefix" in str(out["error"])


async def test_log_missing_card_returns_404(cli_env):
    exit_code, out = await _run(cli_env, "card_nonexistent_id")
    assert exit_code != 0
    assert "not found" in str(out["error"])


async def test_log_missing_session_returns_404(cli_env):
    exit_code, out = await _run(cli_env, "sess_nonexistent_id")
    assert exit_code != 0
    assert "not found" in str(out["error"])

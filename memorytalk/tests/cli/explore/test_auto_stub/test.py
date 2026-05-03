"""explore auto — stub returns non-zero with a clear message."""
from __future__ import annotations
import json


def test_auto_exits_nonzero_with_message(explore_env):
    result = explore_env.runner.invoke(explore_env.main, [
        "explore", "auto", "--data-root", str(explore_env.data_root),
    ])
    assert result.exit_code == 1
    assert "not implemented" in result.stderr


def test_auto_json_mode(explore_env):
    result = explore_env.runner.invoke(explore_env.main, [
        "explore", "auto", "--data-root", str(explore_env.data_root), "--json",
    ])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert "not implemented" in payload["error"]

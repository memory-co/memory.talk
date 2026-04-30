"""review detail — unknown session_id (no recall history) returns 404."""
from __future__ import annotations
import json


async def test_unknown_session_returns_404(cli_env):
    result = cli_env.runner.invoke(cli_env.main, [
        "review", "detail", "never-recalled",
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    err_str = json.dumps(payload, ensure_ascii=False)
    assert "not found" in err_str.lower()

"""While `app.state.status="rebuilding"`, the search CLI hits the 503 gate."""
from __future__ import annotations
import json

from memory_talk_v2.schemas import (
    ContentBlock, IngestRound, IngestSessionRequest,
)


async def _seed(cli_env):
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="platform-a", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="hello")],
            is_sidechain=False,
        )],
    ))


async def _run_search(cli_env, query: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "search", query,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def test_search_blocked_while_rebuilding(cli_env):
    await _seed(cli_env)
    cli_env.app.state.status = "rebuilding"
    try:
        exit_code, out = await _run_search(cli_env, "hello")
        assert exit_code != 0
        assert "rebuilding" in json.dumps(out["error"], ensure_ascii=False)
    finally:
        cli_env.app.state.status = "running"


async def test_search_resumes_after_rebuild_completes(cli_env):
    await _seed(cli_env)
    cli_env.app.state.status = "rebuilding"
    exit_code, _ = await _run_search(cli_env, "hello")
    assert exit_code != 0

    cli_env.app.state.status = "running"
    exit_code, out = await _run_search(cli_env, "hello")
    assert exit_code == 0, out


async def test_status_still_reachable_during_rebuild(cli_env):
    cli_env.app.state.status = "rebuilding"
    try:
        result = cli_env.runner.invoke(cli_env.main, [
            "server", "status",
            "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
        assert result.exit_code == 0
        out = json.loads(result.stdout)
        assert out["status"] == "rebuilding"
    finally:
        cli_env.app.state.status = "running"

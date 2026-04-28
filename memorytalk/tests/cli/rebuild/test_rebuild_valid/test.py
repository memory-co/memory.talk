"""`memory-talk rebuild` — happy path: rebuild restores SQLite from file-layer truth."""
from __future__ import annotations
import json

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest,
    IngestRound, IngestSessionRequest,
)


async def _seed(cli_env):
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="platform-a", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="hello world")],
            is_sidechain=False,
        )],
    ))
    await cli_env.app.state.cards.create(CreateCardRequest(
        summary="a card about hello",
        rounds=[CardRoundsItem(session_id="sess_platform-a", indexes="1")],
    ))


async def _run_rebuild(cli_env) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "rebuild",
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def _run_search(cli_env, query: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "search", query,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def test_rebuild_returns_counts(cli_env):
    await _seed(cli_env)
    exit_code, out = await _run_rebuild(cli_env)
    assert exit_code == 0, out
    assert out["status"] == "ok"
    assert out["sessions"] == 1
    assert out["cards"] == 1
    assert out["errors_count"] == 0


async def test_status_back_to_running_after_rebuild(cli_env):
    await _seed(cli_env)
    await _run_rebuild(cli_env)
    assert cli_env.app.state.status == "running"

    result = cli_env.runner.invoke(cli_env.main, [
        "server", "status",
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    status = json.loads(result.stdout)
    assert status["status"] == "running"


async def test_search_works_after_rebuild(cli_env):
    await _seed(cli_env)
    await _run_rebuild(cli_env)
    exit_code, out = await _run_search(cli_env, "hello")
    assert exit_code == 0, out
    # FTS index was dropped + recreated by rebuild — must still find the seeded data
    assert out["cards"]["count"] == 1
    assert out["sessions"]["count"] == 1

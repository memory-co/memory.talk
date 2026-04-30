"""review list — session_exist reflects sessions-table membership."""
from __future__ import annotations
import json

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest,
    IngestRound, IngestSessionRequest,
)


async def _ingest_session(cli_env, sid: str, text: str):
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id=sid, source="claude-code", created_at="",
        metadata={}, sha256=f"h-{sid}",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text=text)],
            is_sidechain=False,
        )],
    ))


async def _recall(cli_env, sid: str, prompt: str):
    result = cli_env.runner.invoke(cli_env.main, [
        "recall", sid, prompt,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, result.stdout


async def test_session_exist_distinguishes_ingested_vs_recall_only(cli_env):
    # Source session + one card so recall has something to surface.
    await _ingest_session(cli_env, "src", "LanceDB content")
    await cli_env.app.state.cards.create(CreateCardRequest(
        summary="card",
        rounds=[CardRoundsItem(session_id="sess_src", indexes="1")],
    ))

    # session A: ingested AND recalled
    await _ingest_session(cli_env, "alpha", "alpha session content")
    await _recall(cli_env, "alpha", "LanceDB")

    # session B: only recalled, never ingested
    await _recall(cli_env, "beta-unsynced", "LanceDB")

    result = cli_env.runner.invoke(cli_env.main, [
        "review", "list",
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, result.stdout
    sessions = json.loads(result.stdout)["sessions"]
    by_id = {s["session_id"]: s for s in sessions}

    assert by_id["sess_alpha"]["session_exist"] is True
    assert by_id["sess_beta-unsynced"]["session_exist"] is False

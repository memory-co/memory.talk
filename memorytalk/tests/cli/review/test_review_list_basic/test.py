"""review list — multiple sessions sorted by last_at desc."""
from __future__ import annotations
import json

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest,
    IngestRound, IngestSessionRequest,
)


async def _seed_corpus(cli_env):
    """One session + one card so recall has something to retrieve."""
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="src", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="LanceDB content")],
            is_sidechain=False,
        )],
    ))
    await cli_env.app.state.cards.create(CreateCardRequest(
        summary="card LanceDB",
        rounds=[CardRoundsItem(session_id="sess_src", indexes="1")],
    ))


async def _recall(cli_env, sid: str, prompt: str) -> dict:
    result = cli_env.runner.invoke(cli_env.main, [
        "recall", sid, prompt,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, result.stdout
    return json.loads(result.stdout)


async def _review_list(cli_env, limit: int = 100) -> dict:
    result = cli_env.runner.invoke(cli_env.main, [
        "review", "list",
        "--limit", str(limit),
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, result.stdout
    return json.loads(result.stdout)


async def test_review_list_empty_when_no_recall(cli_env):
    out = await _review_list(cli_env)
    assert out == {"sessions": []}


async def test_review_list_returns_all_sessions(cli_env):
    await _seed_corpus(cli_env)
    await _recall(cli_env, "session-A", "first")
    await _recall(cli_env, "session-B", "second")

    out = await _review_list(cli_env)
    sessions = out["sessions"]
    assert len(sessions) == 2
    # Note: dt_to_iso has second-level precision, so two rapid recalls will
    # tie on last_at and the ORDER BY tiebreaker (session_id ASC under SQLite)
    # determines display order. Verify membership rather than position.
    sids = {s["session_id"] for s in sessions}
    assert sids == {"sess_session-A", "sess_session-B"}
    for s in sessions:
        assert s["round_count"] == 1
        assert "session_exist" in s
        assert s["session_exist"] is False  # neither was ingested via /v2/sessions
        assert "cards_injected" in s
        assert "last_query" in s

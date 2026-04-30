"""recall — first call for a brand-new session_id (session not in v2 yet)."""
from __future__ import annotations
import json

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest,
    IngestRound, IngestSessionRequest,
)


async def _seed(cli_env):
    """Seed one session + one card so recall has something to retrieve."""
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="src", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="LanceDB intro")],
            is_sidechain=False,
        )],
    ))
    await cli_env.app.state.cards.create(CreateCardRequest(
        summary="LanceDB selection",
        rounds=[CardRoundsItem(session_id="sess_src", indexes="1")],
    ))


async def _run(cli_env, session_id: str, prompt: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "recall", session_id, prompt,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def test_first_recall_for_new_session(cli_env):
    await _seed(cli_env)
    # Use a session_id that does NOT exist in v2 yet — recall must accept this.
    exit_code, out = await _run(cli_env, "in-flight-session", "LanceDB")
    assert exit_code == 0, out
    assert out["session_id"] == "sess_in-flight-session"
    assert out["round_count"] == 1
    assert out["query"] == "LanceDB"
    assert isinstance(out["recalled"], list)
    assert isinstance(out["skipped_already_recalled"], list)
    assert out["skipped_already_recalled"] == []
    # Should retrieve at least one card (LanceDB matches the seeded card)
    assert len(out["recalled"]) >= 1
    for hit in out["recalled"]:
        assert hit["card_id"].startswith("card_")
        assert hit["summary"]

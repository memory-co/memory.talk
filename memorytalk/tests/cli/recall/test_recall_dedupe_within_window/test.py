"""recall — same prompt twice in a row dedupes the second hit."""
from __future__ import annotations
import json

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest,
    IngestRound, IngestSessionRequest,
)


async def _seed(cli_env):
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="src", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="unique-keyword content")],
            is_sidechain=False,
        )],
    ))
    await cli_env.app.state.cards.create(CreateCardRequest(
        summary="card about unique-keyword",
        rounds=[CardRoundsItem(session_id="sess_src", indexes="1")],
    ))


async def _run(cli_env, session_id: str, prompt: str) -> dict:
    result = cli_env.runner.invoke(cli_env.main, [
        "recall", session_id, prompt,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, result.stdout
    return json.loads(result.stdout)


async def test_same_prompt_twice_dedupes(cli_env):
    await _seed(cli_env)

    first = await _run(cli_env, "live-session", "unique-keyword")
    assert first["round_count"] == 1
    assert len(first["recalled"]) >= 1
    first_card_ids = [h["card_id"] for h in first["recalled"]]
    assert first["skipped_already_recalled"] == []

    second = await _run(cli_env, "live-session", "unique-keyword")
    assert second["round_count"] == 2
    second_card_ids = [h["card_id"] for h in second["recalled"]]
    # First-recalled cards should now be in skipped, not in recalled
    for cid in first_card_ids:
        assert cid not in second_card_ids
        assert cid in second["skipped_already_recalled"]

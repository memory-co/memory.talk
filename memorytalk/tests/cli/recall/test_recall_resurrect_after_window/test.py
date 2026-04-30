"""recall — sliding window lets old cards reappear once they fall out of K."""
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
            content=[ContentBlock(type="text", text="resurrect-keyword content")],
            is_sidechain=False,
        )],
    ))
    await cli_env.app.state.cards.create(CreateCardRequest(
        summary="card about resurrect-keyword",
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


async def test_card_resurrects_when_out_of_window(cli_env):
    """With dedup_window_rounds=2:
       round 1: card surfaces and gets recorded
       round 2: same card → skipped (still in window: round 1 > 2 - 2 = 0)
       round 3: same card → recalled again (round 1 NOT > 3 - 2 = 1)"""
    cli_env.app.state.config.settings.recall.dedup_window_rounds = 2
    await _seed(cli_env)

    # round 1
    r1 = await _run(cli_env, "live-session", "resurrect-keyword")
    assert r1["round_count"] == 1
    surfaced = [h["card_id"] for h in r1["recalled"]]
    assert surfaced, "round 1 should surface the seeded card"
    target = surfaced[0]

    # round 2: should still dedupe (round 1 is in window)
    r2 = await _run(cli_env, "live-session", "resurrect-keyword")
    assert r2["round_count"] == 2
    r2_ids = [h["card_id"] for h in r2["recalled"]]
    assert target not in r2_ids
    assert target in r2["skipped_already_recalled"]

    # round 3: round 1 has now fallen out of the window (1 NOT > 3 - 2 = 1).
    # However, round 2 is still in the window. The card was NOT recorded in
    # round 2 (skipped rows aren't persisted), so the only memory of the card
    # is round 1, which is now stale. Expectation: card resurrects.
    r3 = await _run(cli_env, "live-session", "resurrect-keyword")
    assert r3["round_count"] == 3
    r3_ids = [h["card_id"] for h in r3["recalled"]]
    assert target in r3_ids, (
        f"card should resurrect at round 3 with window=2, "
        f"recalled={r3_ids} skipped={r3['skipped_already_recalled']}"
    )

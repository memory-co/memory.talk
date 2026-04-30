"""review detail — per-round hit history, most recent round first."""
from __future__ import annotations
import json

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest,
    IngestRound, IngestSessionRequest,
)


async def _seed(cli_env):
    """Two distinct cards so two rounds with different prompts can each
    surface something fresh (no dedup interference)."""
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="src", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[
            IngestRound(
                round_id="r1", parent_id=None, timestamp="",
                speaker="user", role="human",
                content=[ContentBlock(type="text", text="topic-alpha keyword")],
                is_sidechain=False,
            ),
            IngestRound(
                round_id="r2", parent_id="r1", timestamp="",
                speaker="user", role="human",
                content=[ContentBlock(type="text", text="topic-beta keyword")],
                is_sidechain=False,
            ),
        ],
    ))
    await cli_env.app.state.cards.create(CreateCardRequest(
        summary="alpha card", card_id="card_alpha",
        rounds=[CardRoundsItem(session_id="sess_src", indexes="1")],
    ))
    await cli_env.app.state.cards.create(CreateCardRequest(
        summary="beta card", card_id="card_beta",
        rounds=[CardRoundsItem(session_id="sess_src", indexes="2")],
    ))


async def _recall(cli_env, sid: str, prompt: str, top_k: int = 1):
    result = cli_env.runner.invoke(cli_env.main, [
        "recall", sid, prompt,
        "--top-k", str(top_k),
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, result.stdout


async def test_review_detail_two_rounds_descending(cli_env):
    """top_k=1 keeps each round to a single hit so the dedup window doesn't
    swallow round 2 entirely. (With top_k=3, round 1 already grabs both
    cards and round 2 has nothing fresh to surface.)"""
    await _seed(cli_env)
    await _recall(cli_env, "live", "topic-alpha")     # round 1 → card_alpha
    await _recall(cli_env, "live", "topic-beta")      # round 2 → card_beta

    result = cli_env.runner.invoke(cli_env.main, [
        "review", "detail", "live",
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, result.stdout
    detail = json.loads(result.stdout)

    assert detail["session_id"] == "sess_live"
    assert detail["round_count"] == 2
    assert detail["session_exist"] is False
    rounds = detail["rounds"]
    assert len(rounds) == 2
    # most recent first
    assert rounds[0]["round_count"] == 2
    assert rounds[1]["round_count"] == 1
    assert rounds[0]["query"] == "topic-beta"
    assert rounds[1]["query"] == "topic-alpha"
    # each round has at least one hit with card_id + rank
    for r in rounds:
        assert r["hits"]
        for h in r["hits"]:
            assert h["card_id"].startswith("card_")
            assert h["rank"] >= 1

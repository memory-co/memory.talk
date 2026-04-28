"""`memory-talk link create <json>` — all the rejection paths.

Every invalid request must exit non-zero with {"error": ...} and must
NOT create any link (assert links.count() unchanged).
"""
from __future__ import annotations
import json

import pytest

from memorytalk.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest, IngestRound, IngestSessionRequest,
)


async def _seed(cli_env):
    """One session, one card — enough for valid endpoints in error cases."""
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="platform-a", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="hi")],
            is_sidechain=False,
        )],
    ))
    card_id = (await cli_env.app.state.cards.create(CreateCardRequest(
        summary="c", rounds=[CardRoundsItem(session_id="sess_platform-a", indexes="1")],
    ))).card_id
    return "sess_platform-a", card_id


async def _run(cli_env, body: dict) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "link", "create", json.dumps(body, ensure_ascii=False),
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def test_self_loop_rejected(cli_env):
    sid, card_id = await _seed(cli_env)
    before = await cli_env.app.state.db.links.count()
    exit_code, out = await _run(cli_env, {
        "source_id": card_id, "source_type": "card",
        "target_id": card_id, "target_type": "card",
    })
    assert exit_code != 0
    assert "self-loop" in str(out["error"])
    # Default link from card creation already exists (card → session), so just
    # verify count did NOT increase from the self-loop attempt.
    assert await cli_env.app.state.db.links.count() == before


async def test_type_mismatch_rejected(cli_env):
    sid, card_id = await _seed(cli_env)
    before = await cli_env.app.state.db.links.count()
    exit_code, out = await _run(cli_env, {
        # source_id is a card but source_type claims it's a session
        "source_id": card_id, "source_type": "session",
        "target_id": sid, "target_type": "session",
    })
    assert exit_code != 0
    assert "type mismatch" in str(out["error"]) or "prefix" in str(out["error"])
    assert await cli_env.app.state.db.links.count() == before


async def test_missing_source_endpoint_rejected(cli_env):
    sid, _ = await _seed(cli_env)
    before = await cli_env.app.state.db.links.count()
    exit_code, out = await _run(cli_env, {
        "source_id": "card_does_not_exist", "source_type": "card",
        "target_id": sid, "target_type": "session",
    })
    assert exit_code != 0
    assert "not found" in str(out["error"])
    assert await cli_env.app.state.db.links.count() == before


async def test_missing_target_endpoint_rejected(cli_env):
    sid, card_id = await _seed(cli_env)
    before = await cli_env.app.state.db.links.count()
    exit_code, out = await _run(cli_env, {
        "source_id": card_id, "source_type": "card",
        "target_id": "sess_nonexistent", "target_type": "session",
    })
    assert exit_code != 0
    assert "not found" in str(out["error"])
    assert await cli_env.app.state.db.links.count() == before


async def test_bad_source_prefix_rejected(cli_env):
    sid, _ = await _seed(cli_env)
    before = await cli_env.app.state.db.links.count()
    exit_code, out = await _run(cli_env, {
        "source_id": "not-a-valid-id", "source_type": "card",
        "target_id": sid, "target_type": "session",
    })
    assert exit_code != 0
    assert "prefix" in str(out["error"]) or "type mismatch" in str(out["error"])
    assert await cli_env.app.state.db.links.count() == before


async def test_comment_too_long_rejected(cli_env):
    sid, card_id = await _seed(cli_env)
    # Default max is 500 chars (settings.search.comment_max_length)
    before = await cli_env.app.state.db.links.count()
    exit_code, out = await _run(cli_env, {
        "source_id": card_id, "source_type": "card",
        "target_id": sid, "target_type": "session",
        "comment": "x" * 501,
    })
    assert exit_code != 0
    assert "too long" in str(out["error"])
    assert await cli_env.app.state.db.links.count() == before

"""`memory-talk card <json>` with malformed / out-of-range indexes — error path.

All these cases must:
- exit non-zero
- print a single JSON object `{"error": {...}}` on stdout (no traceback)
- NOT create any card (SQLite `cards` table stays empty after)
"""
from __future__ import annotations
import json

import pytest

from memorytalk.schemas import ContentBlock, IngestRound, IngestSessionRequest


async def _seed_session(cli_env, *, rounds_count=5) -> str:
    rounds = [
        IngestRound(
            round_id=f"r{i}", parent_id=None, timestamp="",
            speaker="user" if i % 2 else "assistant",
            role="human" if i % 2 else "assistant",
            content=[ContentBlock(type="text", text=f"round {i} text")],
            is_sidechain=False, cwd=None,
        )
        for i in range(1, rounds_count + 1)
    ]
    r = await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="platform-abc", source="claude-code", created_at="",
        metadata={}, sha256="h", rounds=rounds,
    ))
    return r.session_id


async def _run_card(cli_env, body: dict) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "card", json.dumps(body, ensure_ascii=False),
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


@pytest.mark.parametrize("bad_indexes, expected_substring", [
    # session has rounds 1..5; 99 is out of range
    ("1-99",               "out of range"),
    # non-monotonic list
    ("5,3",                "monotonically increasing"),
    # non-numeric token
    ("abc",                "bad index"),
    # descending range (ai > bi)
    ("5-2",                "not ascending"),
    # empty after stripping
    ("  ",                 "empty indexes"),
])
async def test_card_rejects_bad_indexes(cli_env, bad_indexes, expected_substring):
    sid = await _seed_session(cli_env, rounds_count=5)

    before_count = await cli_env.app.state.db.cards.count()

    exit_code, out = await _run_card(cli_env, {
        "summary": "won't land",
        "rounds": [{"session_id": sid, "indexes": bad_indexes}],
    })

    # CLI should exit non-zero with a JSON error payload
    assert exit_code != 0, f"expected non-zero exit for indexes={bad_indexes!r}, got exit=0 out={out}"
    assert "error" in out, f"expected error key for indexes={bad_indexes!r}, got {out}"
    # The api() helper returns ApiError.payload which is FastAPI's {"detail": "..."}.
    # Convert to string for substring match.
    assert expected_substring in str(out["error"]), (
        f"expected {expected_substring!r} in error for indexes={bad_indexes!r}, got {out['error']!r}"
    )

    # No card should have been created
    after_count = await cli_env.app.state.db.cards.count()
    assert after_count == before_count, (
        f"card was created despite invalid indexes={bad_indexes!r}"
    )


async def test_card_rejects_missing_session(cli_env):
    # indexes syntactically fine, but session doesn't exist
    before_count = await cli_env.app.state.db.cards.count()
    exit_code, out = await _run_card(cli_env, {
        "summary": "no such session",
        "rounds": [{"session_id": "sess_does_not_exist", "indexes": "1-3"}],
    })
    assert exit_code != 0
    assert "error" in out
    assert "session not found" in str(out["error"])
    assert (await cli_env.app.state.db.cards.count()) == before_count


async def test_card_rejects_bad_session_prefix(cli_env):
    # session_id doesn't start with sess_ — caught before even looking up
    before_count = await cli_env.app.state.db.cards.count()
    exit_code, out = await _run_card(cli_env, {
        "summary": "bad prefix",
        "rounds": [{"session_id": "not-a-session-id", "indexes": "1-3"}],
    })
    assert exit_code != 0
    assert "error" in out
    assert "invalid session_id prefix" in str(out["error"])
    assert (await cli_env.app.state.db.cards.count()) == before_count

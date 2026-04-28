"""`memory-talk card <json>` with valid indexes — happy path."""
from __future__ import annotations
import json

from memorytalk.schemas import ContentBlock, IngestRound, IngestSessionRequest


async def _seed_session(cli_env, *, rounds_count=5) -> str:
    """Seed via service directly — card tests focus on `card` CLI, not ingest."""
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


async def test_card_with_range_indexes(cli_env):
    sid = await _seed_session(cli_env, rounds_count=5)
    exit_code, out = await _run_card(cli_env, {
        "summary": "selected LanceDB",
        "rounds": [{"session_id": sid, "indexes": "1-3"}],
    })
    assert exit_code == 0, out
    assert out["status"] == "ok"
    assert out["card_id"].startswith("card_")


async def test_card_with_list_indexes(cli_env):
    sid = await _seed_session(cli_env, rounds_count=5)
    exit_code, out = await _run_card(cli_env, {
        "summary": "pick rounds 1, 3, 5",
        "rounds": [{"session_id": sid, "indexes": "1,3,5"}],
    })
    assert exit_code == 0, out
    assert out["card_id"].startswith("card_")


async def test_card_with_mixed_range_and_list(cli_env):
    sid = await _seed_session(cli_env, rounds_count=10)
    exit_code, out = await _run_card(cli_env, {
        "summary": "mix",
        "rounds": [{"session_id": sid, "indexes": "1-3,6,9-10"}],
    })
    assert exit_code == 0, out
    assert out["card_id"].startswith("card_")


async def test_card_with_single_index(cli_env):
    sid = await _seed_session(cli_env, rounds_count=3)
    exit_code, out = await _run_card(cli_env, {
        "summary": "one round",
        "rounds": [{"session_id": sid, "indexes": "2"}],
    })
    assert exit_code == 0, out
    assert out["card_id"].startswith("card_")


async def test_card_spanning_two_sessions(cli_env):
    # Seed two sessions
    sid_a = await _seed_session(cli_env, rounds_count=3)
    # Re-seed with a different session_id — _seed_session hardcodes "platform-abc",
    # so build a second one inline
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="platform-def", source="claude-code", created_at="",
        metadata={}, sha256="h2",
        rounds=[IngestRound(
            round_id=f"x{i}", parent_id=None, timestamp="",
            speaker="user" if i % 2 else "assistant",
            role="human" if i % 2 else "assistant",
            content=[ContentBlock(type="text", text=f"other {i}")],
            is_sidechain=False,
        ) for i in range(1, 4)],
    ))
    sid_b = "sess_platform-def"

    exit_code, out = await _run_card(cli_env, {
        "summary": "cross-session card",
        "rounds": [
            {"session_id": sid_a, "indexes": "1-2"},
            {"session_id": sid_b, "indexes": "1,3"},
        ],
    })
    assert exit_code == 0, out
    assert out["card_id"].startswith("card_")

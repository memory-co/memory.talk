"""`memory-talk link create <json>` — valid user link creation."""
from __future__ import annotations
import json

from memory_talk_v2.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest, IngestRound, IngestSessionRequest,
)


async def _seed(cli_env):
    """Two sessions + two cards so we can exercise all link topologies."""
    for raw in ("platform-a", "platform-b"):
        await cli_env.app.state.sessions.ingest(IngestSessionRequest(
            session_id=raw, source="claude-code", created_at="",
            metadata={}, sha256=f"h-{raw}",
            rounds=[IngestRound(
                round_id=f"{raw}_r1", parent_id=None, timestamp="",
                speaker="user", role="human",
                content=[ContentBlock(type="text", text=f"hi from {raw}")],
                is_sidechain=False,
            )],
        ))
    card1 = (await cli_env.app.state.cards.create(CreateCardRequest(
        summary="card one",
        rounds=[CardRoundsItem(session_id="sess_platform-a", indexes="1")],
    ))).card_id
    card2 = (await cli_env.app.state.cards.create(CreateCardRequest(
        summary="card two",
        rounds=[CardRoundsItem(session_id="sess_platform-b", indexes="1")],
    ))).card_id
    return "sess_platform-a", "sess_platform-b", card1, card2


async def _run(cli_env, body: dict) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "link", "create", json.dumps(body, ensure_ascii=False),
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def test_link_card_to_session(cli_env):
    sid_a, _, card1, _ = await _seed(cli_env)
    exit_code, out = await _run(cli_env, {
        "source_id": card1, "source_type": "card",
        "target_id": sid_a, "target_type": "session",
        "comment": "extracted from here",
    })
    assert exit_code == 0, out
    assert out["status"] == "ok"
    assert out["link_id"].startswith("link_")
    assert out["ttl"] == cli_env.config.settings.ttl.link.initial


async def test_link_card_to_card_with_comment(cli_env):
    _, _, card1, card2 = await _seed(cli_env)
    exit_code, out = await _run(cli_env, {
        "source_id": card1, "source_type": "card",
        "target_id": card2, "target_type": "card",
        "comment": "followup decision",
    })
    assert exit_code == 0, out
    link = await cli_env.app.state.db.links.get(out["link_id"])
    assert link["comment"] == "followup decision"
    assert link["source_id"] == card1 and link["target_id"] == card2


async def test_link_session_to_session(cli_env):
    sid_a, sid_b, _, _ = await _seed(cli_env)
    exit_code, out = await _run(cli_env, {
        "source_id": sid_a, "source_type": "session",
        "target_id": sid_b, "target_type": "session",
    })
    assert exit_code == 0, out
    assert out["link_id"].startswith("link_")


async def test_link_create_emits_events_on_both_ends(cli_env):
    sid_a, _, card1, _ = await _seed(cli_env)
    exit_code, out = await _run(cli_env, {
        "source_id": card1, "source_type": "card",
        "target_id": sid_a, "target_type": "session",
    })
    assert exit_code == 0

    # Source side: outgoing event with peer = target
    card_events = [
        e for e in await _card_events(cli_env, card1)
        if e["kind"] == "linked" and e["detail"]["direction"] == "outgoing"
    ]
    assert len(card_events) == 1
    assert card_events[0]["detail"]["peer_id"] == sid_a

    # Target side: incoming event with peer = source
    sess_events = [
        e for e in await _session_events(cli_env, sid_a)
        if e["kind"] == "linked" and e["detail"]["direction"] == "incoming"
    ]
    assert len(sess_events) == 1
    assert sess_events[0]["detail"]["peer_id"] == card1


async def _card_events(cli_env, card_id: str) -> list[dict]:
    return await cli_env.app.state.db.cards.read_events(card_id)


async def _session_events(cli_env, session_id: str) -> list[dict]:
    db = cli_env.app.state.db
    s = await db.sessions.get(session_id)
    return await db.sessions.read_events(s["source"], session_id)

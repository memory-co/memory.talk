"""`memory-talk log <id>` — read the lifecycle event stream of a card or session."""
from __future__ import annotations
import json

from memory_talk_v2.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest, CreateLinkRequest,
    IngestRound, IngestSessionRequest, TagsRequest,
)


async def _seed(cli_env):
    """Build a session → card → link → tag trail so multiple events accumulate."""
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
    sid = "sess_platform-a"
    card_id = (await cli_env.app.state.cards.create(CreateCardRequest(
        summary="c", rounds=[CardRoundsItem(session_id=sid, indexes="1")],
    ))).card_id
    await cli_env.app.state.links.create(CreateLinkRequest(
        source_id=card_id, source_type="card",
        target_id=sid, target_type="session", comment="x",
    ))
    await cli_env.app.state.sessions.add_tags(TagsRequest(
        session_id=sid, tags=["decision"],
    ))
    return sid, card_id


async def _run(cli_env, object_id: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "log", object_id,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, json.loads(result.stdout)


async def test_log_session_streams_all_lifecycle_events(cli_env):
    sid, card_id = await _seed(cli_env)
    exit_code, out = await _run(cli_env, sid)
    assert exit_code == 0, out
    assert out["type"] == "session"
    assert out["session_id"] == sid

    kinds = [e["kind"] for e in out["events"]]
    assert "imported" in kinds
    assert "card_extracted" in kinds
    assert "linked" in kinds
    assert "tag_added" in kinds


async def test_log_card_streams_created_and_linked(cli_env):
    _, card_id = await _seed(cli_env)
    exit_code, out = await _run(cli_env, card_id)
    assert exit_code == 0, out
    assert out["type"] == "card"
    assert out["card_id"] == card_id

    kinds = [e["kind"] for e in out["events"]]
    # created first (from CardService.create), then linked (from LinkService.create)
    assert kinds == ["created", "linked"]


async def test_log_events_sorted_ascending_by_at(cli_env):
    sid, card_id = await _seed(cli_env)
    _, out = await _run(cli_env, sid)
    # Every at must be monotonically non-decreasing (asc sort, ties allowed)
    times = [e["at"] for e in out["events"]]
    assert times == sorted(times), f"events not sorted ascending: {times}"


async def test_log_event_detail_shape(cli_env):
    sid, card_id = await _seed(cli_env)
    _, out = await _run(cli_env, card_id)

    created = next(e for e in out["events"] if e["kind"] == "created")
    detail = created["detail"]
    assert detail["summary"] == "c"
    assert detail["rounds"] == [{"session_id": sid, "indexes": "1"}]
    assert len(detail["default_links"]) == 1
    assert detail["default_links"][0]["target_id"] == sid
    assert detail["ttl_initial"] == cli_env.config.settings.ttl.card.initial

    linked = next(e for e in out["events"] if e["kind"] == "linked")
    assert linked["detail"]["direction"] == "outgoing"
    assert linked["detail"]["peer_id"] == sid
    assert linked["detail"]["peer_type"] == "session"
    assert linked["detail"]["comment"] == "x"

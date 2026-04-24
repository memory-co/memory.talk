"""Card creation: validation, default links, events, embeddings."""
from __future__ import annotations

import pytest

from memory_talk_v2.service import CardConflictError, CardServiceError
from memory_talk_v2.service.cards import compact_indexes, parse_indexes


async def _seed_session(services, *, session_id="platform-abc", rounds_count=5) -> str:
    rounds = []
    for i in range(1, rounds_count + 1):
        rounds.append({
            "round_id": f"r{i}", "parent_id": None, "timestamp": "2026-04-10T00:00:00Z",
            "speaker": "user" if i % 2 else "assistant",
            "role": "human" if i % 2 else "assistant",
            "content": [{"type": "text", "text": f"round {i} text"}],
            "is_sidechain": False, "cwd": None,
        })
    r = await services.sessions.ingest(
        {"session_id": session_id, "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": f"sha-{session_id}", "rounds": rounds},
    )
    return r["session_id"]


def test_parse_indexes_range():
    assert parse_indexes("11-15") == [11, 12, 13, 14, 15]


def test_parse_indexes_list():
    assert parse_indexes("3,7,12") == [3, 7, 12]


def test_parse_indexes_monotonic_check():
    with pytest.raises(CardServiceError):
        parse_indexes("5,3")


def test_compact_indexes():
    assert compact_indexes([11, 12, 13, 14, 15]) == "11-15"
    assert compact_indexes([11, 12, 13, 15, 16]) == "11-13,15-16"
    assert compact_indexes([3, 7, 12]) == "3,7,12"
    assert compact_indexes([5]) == "5"


async def test_create_card_happy_path(services):
    sid = await _seed_session(services, rounds_count=5)
    result = await services.cards.create(
        {"summary": "selected LanceDB", "rounds": [{"session_id": sid, "indexes": "1-3"}]},
    )
    assert result["status"] == "ok"
    card_id = result["card_id"]

    card = await services.db.cards.get(card_id)
    assert card["summary"] == "selected LanceDB"
    assert [r["index"] for r in card["rounds"]] == [1, 2, 3]
    assert card["rounds"][0]["session_id"] == sid

    links = await services.db.links.touching(card_id)
    assert len(links) == 1
    assert links[0]["source_id"] == card_id and links[0]["target_id"] == sid
    assert links[0]["expires_at"] is None

    card_events = await services.events_for(card_id)
    assert card_events[0]["kind"] == "created"
    assert card_events[0]["detail"]["summary"] == "selected LanceDB"
    assert card_events[0]["detail"]["default_links"][0]["target_id"] == sid

    sess_events = await services.events_for(sid)
    kinds = [e["kind"] for e in sess_events]
    assert "card_extracted" in kinds
    extracted = next(e for e in sess_events if e["kind"] == "card_extracted")
    assert extracted["detail"]["indexes"] == "1-3"


async def test_create_card_with_from_search_id_passes_through(services):
    sid = await _seed_session(services)
    result = await services.cards.create(
        {"summary": "x", "rounds": [{"session_id": sid, "indexes": "1-2"}],
         "from_search_id": "sch_demo"},
    )
    ev = (await services.events_for(result["card_id"]))[0]
    assert ev["detail"]["from_search_id"] == "sch_demo"


async def test_create_card_rejects_bad_session_prefix(services):
    with pytest.raises(CardServiceError, match="invalid session_id prefix"):
        await services.cards.create(
            {"summary": "x", "rounds": [{"session_id": "nope", "indexes": "1"}]},
        )


async def test_create_card_rejects_out_of_range(services):
    sid = await _seed_session(services, rounds_count=3)
    with pytest.raises(CardServiceError, match="out of range"):
        await services.cards.create(
            {"summary": "x", "rounds": [{"session_id": sid, "indexes": "1-99"}]},
        )


async def test_create_card_rejects_duplicate_id(services):
    sid = await _seed_session(services)
    r1 = await services.cards.create(
        {"summary": "x", "rounds": [{"session_id": sid, "indexes": "1-2"}]},
    )
    with pytest.raises(CardConflictError):
        await services.cards.create(
            {"summary": "y", "card_id": r1["card_id"],
             "rounds": [{"session_id": sid, "indexes": "1-2"}]},
        )


async def test_card_extracted_merges_same_session(services):
    sid = await _seed_session(services, rounds_count=25)
    await services.cards.create(
        {"summary": "s",
         "rounds": [{"session_id": sid, "indexes": "1-3"},
                    {"session_id": sid, "indexes": "20,22"}]},
    )
    sess_events = [e for e in await services.events_for(sid) if e["kind"] == "card_extracted"]
    assert len(sess_events) == 1
    assert sess_events[0]["detail"]["indexes"] == "1-3,20,22"

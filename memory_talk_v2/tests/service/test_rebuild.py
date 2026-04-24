"""Rebuild: drop SQLite, restore objects from files. Events stay in place."""
from __future__ import annotations


async def test_rebuild_preserves_objects_and_events(services):
    await services.sessions.ingest(
        {"session_id": "platform-a", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "hello"}], "is_sidechain": False}]},
    )
    card_id = (await services.cards.create(
        {"summary": "s", "rounds": [{"session_id": "sess_platform-a", "indexes": "1"}]},
    ))["card_id"]
    await services.links.create(
        {"source_id": card_id, "source_type": "card",
         "target_id": "sess_platform-a", "target_type": "session", "comment": "x"},
    )

    before_card = await services.db.cards.get(card_id)
    before_card_events = await services.events_for(card_id)
    before_sess_events = await services.events_for("sess_platform-a")
    assert len(before_card_events) >= 2
    assert len(before_sess_events) >= 3

    r = await services.rebuild.rebuild()
    assert r["status"] == "ok"
    assert r["sessions"] == 1
    assert r["cards"] == 1

    after_card = await services.db.cards.get(card_id)
    assert after_card["expires_at"] == before_card["expires_at"]
    assert (await services.db.sessions.get("sess_platform-a"))["round_count"] == 1

    assert await services.events_for(card_id) == before_card_events
    assert await services.events_for("sess_platform-a") == before_sess_events

    links = await services.db.links.touching(card_id)
    assert any(l["expires_at"] is None for l in links)
    assert any(l["expires_at"] is not None for l in links)

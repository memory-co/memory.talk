"""Rebuild: drop SQLite, restore objects from files. Events stay in place."""
from __future__ import annotations

from memory_talk_v2.service.cards import create_card
from memory_talk_v2.service.links import create_user_link
from memory_talk_v2.service.rebuild import rebuild
from memory_talk_v2.service.sessions import ingest_session


def test_rebuild_preserves_objects_and_events(services):
    ingest_session(
        {"session_id": "platform-a", "source": "claude-code", "created_at": "",
         "metadata": {}, "sha256": "h",
         "rounds": [{"round_id": "r1", "parent_id": None, "timestamp": "",
                     "speaker": "user", "role": "human",
                     "content": [{"type": "text", "text": "hello"}], "is_sidechain": False}]},
        db=services.db, vectors=services.vectors, events=services.events,
        sessions_root=services.config.sessions_dir,
    )
    card_id = create_card(
        {"summary": "s", "rounds": [{"session_id": "sess_platform-a", "indexes": "1"}]},
        config=services.config, db=services.db, vectors=services.vectors,
        embedder=services.embedder, events=services.events,
    )["card_id"]
    create_user_link(
        {"source_id": card_id, "source_type": "card",
         "target_id": "sess_platform-a", "target_type": "session", "comment": "x"},
        config=services.config, db=services.db, events=services.events,
    )

    before_card = services.db.get_card(card_id)
    before_card_events = services.events_for(card_id)
    before_sess_events = services.events_for("sess_platform-a")
    assert len(before_card_events) >= 2            # created + linked
    assert len(before_sess_events) >= 3            # imported + card_extracted + linked

    r = rebuild(config=services.config, db=services.db, vectors=services.vectors,
                embedder=services.embedder)
    assert r["status"] == "ok"
    assert r["sessions"] == 1
    assert r["cards"] == 1
    # Rebuild does not have an events_replayed counter in v2 — events live
    # inside each object's own events.jsonl and never leave during rebuild.
    assert "events_replayed" not in r

    # Objects still there, TTL preserved
    after_card = services.db.get_card(card_id)
    assert after_card["expires_at"] == before_card["expires_at"]
    assert services.db.get_session("sess_platform-a")["round_count"] == 1

    # Events file-resident: unchanged by rebuild
    assert services.events_for(card_id) == before_card_events
    assert services.events_for("sess_platform-a") == before_sess_events

    # Default link + user link both rebuilt
    links = services.db.links_touching(card_id)
    assert any(l["expires_at"] is None for l in links)
    assert any(l["expires_at"] is not None for l in links)

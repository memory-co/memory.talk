"""Unit tests for storage layer."""

from datetime import datetime

import pytest

from memory_talk.models import (
    CardLink,
    RawRef,
    Round,
    Session,
    TalkCard,
    TextBlock,
)
from memory_talk.storage.card_store import CardStore
from memory_talk.storage.session_store import SessionStore
from memory_talk.storage.sqlite_store import SQLiteRelationStore


class TestSQLiteRelationStore:
    @pytest.fixture
    def store(self, temp_dir):
        return SQLiteRelationStore(temp_dir / "relation.db")

    def test_save_and_get_card(self, store):
        card = TalkCard(
            card_id="card-001",
            cognition_summary="Test summary",
            compressed_rounds="Test rounds",
            raw_ref=RawRef(session_id="sess-001", round_start=0, round_end=3),
        )
        store.save_card(card)
        result = store.get_card("card-001")
        assert result is not None
        assert result["card_id"] == "card-001"
        assert result["cognition_summary"] == "Test summary"

    def test_get_card_not_found(self, store):
        assert store.get_card("nonexistent") is None

    def test_list_cards(self, store):
        for i in range(3):
            card = TalkCard(
                card_id=f"card-{i:03d}",
                cognition_summary=f"Summary {i}",
                compressed_rounds=f"Rounds {i}",
                raw_ref=RawRef(session_id="sess-001", round_start=i, round_end=i + 1),
            )
            store.save_card(card)
        assert len(store.list_cards()) == 3
        assert len(store.list_cards(session_id="sess-001")) == 3
        assert len(store.list_cards(session_id="sess-999")) == 0

    def test_save_card_with_links(self, store):
        card = TalkCard(
            card_id="card-a",
            cognition_summary="A",
            compressed_rounds="A rounds",
            raw_ref=RawRef(session_id="sess-001", round_start=0, round_end=1),
            links=[
                CardLink(source_card_id="card-a", target_card_id="card-b", link_type="temporal"),
            ],
        )
        store.save_card(card)
        links = store.get_links("card-a")
        assert len(links) == 1
        assert links[0]["link_type"] == "temporal"

    def test_save_link_separately(self, store):
        link = CardLink(source_card_id="card-x", target_card_id="card-y", link_type="causal", weight=0.8)
        store.save_link(link)
        links = store.get_links("card-x")
        assert len(links) == 1
        assert links[0]["weight"] == 0.8

    def test_get_links_bidirectional(self, store):
        link = CardLink(source_card_id="a", target_card_id="b", link_type="topical")
        store.save_link(link)
        assert len(store.get_links("a")) == 1
        assert len(store.get_links("b")) == 1

    def test_get_links_filter_by_type(self, store):
        store.save_link(CardLink(source_card_id="a", target_card_id="b", link_type="temporal"))
        store.save_link(CardLink(source_card_id="a", target_card_id="c", link_type="causal"))
        assert len(store.get_links("a", link_types=["temporal"])) == 1
        assert len(store.get_links("a", link_types=["temporal", "causal"])) == 2

    def test_session_lifecycle(self, store):
        store.save_session("sess-001", "claude-code", {"project": "test"}, 10)
        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["source"] == "claude-code"

        unbuilt = store.list_sessions(unbuilt_only=True)
        assert len(unbuilt) == 1

        store.mark_session_built("sess-001")
        unbuilt = store.list_sessions(unbuilt_only=True)
        assert len(unbuilt) == 0

    def test_ingest_log(self, store):
        assert not store.is_ingested("/path/to/file", "abc123")
        store.log_ingest("/path/to/file", "sess-001", "abc123")
        assert store.is_ingested("/path/to/file", "abc123")
        assert not store.is_ingested("/path/to/file", "different-hash")


class TestSessionStore:
    @pytest.fixture
    def store(self, temp_dir):
        return SessionStore(temp_dir / "sessions")

    def test_save_and_read(self, store):
        session = Session(
            session_id="ab12cd34",
            source="claude-code",
            rounds=[
                Round(round_id="r001", speaker="user", role="human", content=[TextBlock(text="hello")]),
                Round(round_id="r002", speaker="claude", role="assistant", content=[TextBlock(text="hi")]),
            ],
        )
        store.save(session)
        rounds = store.read("claude-code", "ab12cd34")
        assert len(rounds) == 2
        assert rounds[0].speaker == "user"
        assert rounds[1].content[0].text == "hi"

    def test_read_range(self, store):
        session = Session(
            session_id="ab12cd34",
            source="claude-code",
            rounds=[
                Round(round_id=f"r{i:03d}", speaker="user", role="human", content=[TextBlock(text=f"msg {i}")])
                for i in range(10)
            ],
        )
        store.save(session)
        subset = store.read_range("claude-code", "ab12cd34", 2, 5)
        assert len(subset) == 3
        assert subset[0].round_id == "r002"

    def test_read_nonexistent(self, store):
        assert store.read("claude-code", "nonexistent") == []

    def test_exists(self, store):
        assert not store.exists("claude-code", "ab12cd34")
        session = Session(
            session_id="ab12cd34",
            source="claude-code",
            rounds=[Round(round_id="r001", speaker="user", role="human", content=[TextBlock(text="hi")])],
        )
        store.save(session)
        assert store.exists("claude-code", "ab12cd34")

    def test_hash_bucketing(self, store):
        session = Session(
            session_id="ab12cd34",
            source="claude-code",
            rounds=[Round(round_id="r001", speaker="user", role="human", content=[TextBlock(text="hi")])],
        )
        path = store.save(session)
        assert "/claude-code/ab/" in str(path)


class TestCardStore:
    @pytest.fixture
    def store(self, temp_dir):
        return CardStore(temp_dir / "cards")

    def test_save_and_read(self, store):
        card = TalkCard(
            card_id="ab12cd34",
            cognition_summary="Test",
            compressed_rounds="Rounds",
            raw_ref=RawRef(session_id="sess-001", round_start=0, round_end=3),
        )
        store.save(card)
        result = store.read("ab12cd34")
        assert result is not None
        assert result.card_id == "ab12cd34"
        assert result.cognition_summary == "Test"

    def test_read_nonexistent(self, store):
        assert store.read("nonexistent") is None

    def test_exists(self, store):
        assert not store.exists("ab12cd34")
        card = TalkCard(
            card_id="ab12cd34",
            cognition_summary="Test",
            compressed_rounds="Rounds",
            raw_ref=RawRef(session_id="sess-001", round_start=0, round_end=3),
        )
        store.save(card)
        assert store.exists("ab12cd34")

    def test_hash_bucketing(self, store):
        card = TalkCard(
            card_id="ab12cd34",
            cognition_summary="Test",
            compressed_rounds="Rounds",
            raw_ref=RawRef(session_id="sess-001", round_start=0, round_end=3),
        )
        path = store.save(card)
        assert "/ab/" in str(path)

"""Unit tests for data models."""

from datetime import datetime

from memory_talk.models import (
    CardLink,
    CodeBlock,
    RawRef,
    Round,
    Session,
    TalkCard,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


class TestContentBlock:
    def test_text_block(self):
        b = TextBlock(text="hello")
        assert b.type == "text"
        assert b.text == "hello"

    def test_code_block(self):
        b = CodeBlock(language="python", text="print(1)")
        assert b.type == "code"
        assert b.language == "python"

    def test_tool_use_block(self):
        b = ToolUseBlock(name="bash", input="ls")
        assert b.type == "tool_use"

    def test_tool_result_block(self):
        b = ToolResultBlock(output="file.txt")
        assert b.type == "tool_result"


class TestRound:
    def test_round_creation(self):
        r = Round(
            round_id="r001",
            speaker="alice",
            role="human",
            content=[TextBlock(text="hi")],
        )
        assert r.round_id == "r001"
        assert r.speaker == "alice"
        assert r.role == "human"
        assert len(r.content) == 1

    def test_round_with_mixed_content(self):
        r = Round(
            round_id="r002",
            timestamp=datetime(2026, 4, 10, 14, 30),
            speaker="claude",
            role="assistant",
            content=[
                TextBlock(text="Let me check"),
                ToolUseBlock(name="bash", input="ls"),
                ToolResultBlock(output="file.txt"),
                TextBlock(text="Found it"),
            ],
        )
        assert len(r.content) == 4
        assert r.content[0].type == "text"
        assert r.content[1].type == "tool_use"

    def test_round_serialization(self):
        r = Round(
            round_id="r001",
            speaker="alice",
            role="human",
            content=[TextBlock(text="hi")],
        )
        data = r.model_dump()
        r2 = Round.model_validate(data)
        assert r2.round_id == r.round_id
        assert r2.content[0].text == "hi"


class TestSession:
    def test_session_creation(self):
        s = Session(
            session_id="sess-001",
            source="claude-code",
        )
        assert s.session_id == "sess-001"
        assert s.source == "claude-code"
        assert s.rounds == []
        assert s.metadata == {}

    def test_session_with_rounds(self):
        s = Session(
            session_id="sess-001",
            source="claude-code",
            created_at=datetime(2026, 4, 10),
            metadata={"project": "memory-talk", "model": "claude-sonnet-4"},
            rounds=[
                Round(
                    round_id="r001",
                    speaker="user",
                    role="human",
                    content=[TextBlock(text="Hello")],
                ),
                Round(
                    round_id="r002",
                    speaker="claude",
                    role="assistant",
                    content=[TextBlock(text="Hi there")],
                ),
            ],
        )
        assert len(s.rounds) == 2
        assert s.metadata["model"] == "claude-sonnet-4"

    def test_session_serialization_roundtrip(self):
        s = Session(
            session_id="sess-001",
            source="codex",
            rounds=[
                Round(
                    round_id="r001",
                    speaker="user",
                    role="human",
                    content=[TextBlock(text="test")],
                ),
            ],
        )
        data = s.model_dump(mode="json")
        s2 = Session.model_validate(data)
        assert s2.session_id == s.session_id
        assert len(s2.rounds) == 1


class TestTalkCard:
    def test_card_creation(self):
        card = TalkCard(
            card_id="card-001",
            cognition_summary="Decided to use LanceDB for vector storage",
            compressed_rounds="User asked about vector DBs. Discussed options...",
            raw_ref=RawRef(session_id="sess-001", round_start=0, round_end=5),
        )
        assert card.card_id == "card-001"
        assert card.links == []
        assert card.raw_ref.session_id == "sess-001"

    def test_card_with_links(self):
        card = TalkCard(
            card_id="card-002",
            cognition_summary="Performance benchmark results for LanceDB",
            compressed_rounds="Ran benchmarks...",
            raw_ref=RawRef(session_id="sess-001", round_start=6, round_end=10),
            links=[
                CardLink(
                    source_card_id="card-002",
                    target_card_id="card-001",
                    link_type="causal",
                    weight=0.9,
                ),
                CardLink(
                    source_card_id="card-002",
                    target_card_id="card-003",
                    link_type="temporal",
                ),
            ],
        )
        assert len(card.links) == 2
        assert card.links[0].link_type == "causal"
        assert card.links[0].weight == 0.9
        assert card.links[1].weight == 1.0  # default

    def test_card_serialization_roundtrip(self):
        card = TalkCard(
            card_id="card-001",
            cognition_summary="Test summary",
            compressed_rounds="Test rounds",
            raw_ref=RawRef(session_id="sess-001", round_start=0, round_end=3),
            links=[
                CardLink(
                    source_card_id="card-001",
                    target_card_id="card-002",
                    link_type="topical",
                ),
            ],
        )
        data = card.model_dump(mode="json")
        card2 = TalkCard.model_validate(data)
        assert card2.card_id == card.card_id
        assert card2.links[0].link_type == "topical"


class TestRawRef:
    def test_raw_ref(self):
        ref = RawRef(session_id="sess-001", round_start=0, round_end=5)
        assert ref.session_id == "sess-001"
        assert ref.round_start == 0
        assert ref.round_end == 5


class TestCardLink:
    def test_card_link(self):
        link = CardLink(
            source_card_id="a",
            target_card_id="b",
            link_type="temporal",
        )
        assert link.weight == 1.0

    def test_card_link_custom_weight(self):
        link = CardLink(
            source_card_id="a",
            target_card_id="b",
            link_type="causal",
            weight=0.5,
        )
        assert link.weight == 0.5

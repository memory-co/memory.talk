"""Unit tests for models module."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from memory_talk.models import (
    Attachment,
    ConversationMetadata,
    ConversationSummary,
    IngestRequest,
    Message,
    Participant,
    SearchResult,
    SourceStatus,
    ServerStatus,
)


class TestMessage:
    """Test cases for Message model."""

    def test_message_creation(self):
        """Test creating a Message."""
        msg = Message(
            uuid="test-uuid",
            role="user",
            content="Hello",
            timestamp=datetime.now(),
        )

        assert msg.uuid == "test-uuid"
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.parent_uuid is None

    def test_message_with_parent(self):
        """Test Message with parent_uuid."""
        msg = Message(
            uuid="child-uuid",
            parent_uuid="parent-uuid",
            role="user",
            content="Reply",
            timestamp=datetime.now(),
        )

        assert msg.parent_uuid == "parent-uuid"

    def test_message_with_attachments(self):
        """Test Message with attachments."""
        msg = Message(
            uuid="test-uuid",
            role="user",
            content="File attached",
            timestamp=datetime.now(),
            attachments=[
                Attachment(
                    hash="abc123",
                    name="test.txt",
                    size=1024,
                    mime="text/plain",
                )
            ],
        )

        assert len(msg.attachments) == 1
        assert msg.attachments[0].name == "test.txt"


class TestParticipant:
    """Test cases for Participant model."""

    def test_participant_creation(self):
        """Test creating a Participant."""
        participant = Participant(
            name="John",
            role="user",
        )

        assert participant.name == "John"
        assert participant.role == "user"
        assert participant.model is None

    def test_participant_with_model(self):
        """Test Participant with model."""
        participant = Participant(
            name="AI",
            role="assistant",
            model="gpt-4",
        )

        assert participant.model == "gpt-4"


class TestConversationMetadata:
    """Test cases for ConversationMetadata model."""

    def test_metadata_creation(self):
        """Test creating ConversationMetadata."""
        meta = ConversationMetadata(
            session_id="session-001",
            platform="chatgpt",
            title="Test Chat",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            participants=[],
            message_count=10,
        )

        assert meta.session_id == "session-001"
        assert meta.platform == "chatgpt"
        assert meta.message_count == 10


class TestConversationSummary:
    """Test cases for ConversationSummary model."""

    def test_summary_creation(self):
        """Test creating ConversationSummary."""
        summary = ConversationSummary(
            session_id="session-001",
            platform="chatgpt",
            title="Test",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            message_count=5,
        )

        assert summary.message_count == 5


class TestIngestRequest:
    """Test cases for IngestRequest model."""

    def test_ingest_request_creation(self):
        """Test creating IngestRequest."""
        request = IngestRequest(
            platform="chatgpt",
            session_id="session-001",
            messages=[],
            metadata={"title": "Test"},
        )

        assert request.platform == "chatgpt"
        assert request.metadata["title"] == "Test"


class TestSearchResult:
    """Test cases for SearchResult model."""

    def test_search_result_creation(self):
        """Test creating SearchResult."""
        result = SearchResult(
            session_id="session-001",
            platform="chatgpt",
            title="Test Chat",
            matched_message="Found text",
            timestamp=datetime.now(),
        )

        assert result.matched_message == "Found text"


class TestSourceStatus:
    """Test cases for SourceStatus model."""

    def test_source_status_creation(self):
        """Test creating SourceStatus."""
        status = SourceStatus(
            name="test-source",
            status="running",
            messages_synced=100,
        )

        assert status.name == "test-source"
        assert status.status == "running"
        assert status.messages_synced == 100


class TestServerStatus:
    """Test cases for ServerStatus model."""

    def test_server_status_creation(self):
        """Test creating ServerStatus."""
        status = ServerStatus(
            version="0.1.0",
            sources=[],
            total_conversations=10,
            total_messages=100,
            uptime="1 hour",
        )

        assert status.version == "0.1.0"
        assert status.total_conversations == 10
        assert status.total_messages == 100

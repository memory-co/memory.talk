"""Unit tests for storage module."""
import json
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from memory_talk.models import Message
from memory_talk.storage import Storage


class TestStorage:
    """Test cases for Storage class."""

    def test_init_creates_directories(self, temp_dir):
        """Test that Storage creates necessary directories on init."""
        storage = Storage(base_path=temp_dir)

        assert storage.conversations_dir.exists()
        assert storage.blobs_dir.exists()

    def test_save_conversation(self, storage, sample_messages):
        """Test saving a conversation."""
        storage.save_conversation(
            platform="test-platform",
            session_id="session-001",
            messages=sample_messages,
            metadata={"title": "Test Chat"},
        )

        conv_dir = storage._get_conversation_dir("test-platform", "session-001")
        assert conv_dir.exists()

        meta_path = conv_dir / "meta.yaml"
        assert meta_path.exists()

        messages_path = conv_dir / "messages.jsonl"
        assert messages_path.exists()

    def test_save_conversation_updates_metadata(self, storage, sample_messages):
        """Test that metadata is correctly saved."""
        storage.save_conversation(
            platform="test-platform",
            session_id="session-001",
            messages=sample_messages,
            metadata={"title": "My Chat"},
        )

        conv_dir = storage._get_conversation_dir("test-platform", "session-001")
        meta_path = conv_dir / "meta.yaml"

        with open(meta_path) as f:
            meta = yaml.safe_load(f)

        assert meta["title"] == "My Chat"
        assert meta["platform"] == "test-platform"
        assert meta["session_id"] == "session-001"
        assert meta["message_count"] == 2

    def test_save_conversation_deduplication(self, storage):
        """Test that duplicate messages are not saved."""
        messages = [
            Message(
                uuid="msg-001",
                role="user",
                content="Hello",
                timestamp=datetime.now(),
            ),
        ]

        # Save twice
        storage.save_conversation(
            platform="test-platform",
            session_id="session-001",
            messages=messages,
            metadata={},
        )
        storage.save_conversation(
            platform="test-platform",
            session_id="session-001",
            messages=messages,
            metadata={},
        )

        # Should only have one message
        conv_dir = storage._get_conversation_dir("test-platform", "session-001")
        messages_path = conv_dir / "messages.jsonl"

        with open(messages_path) as f:
            lines = f.readlines()

        assert len(lines) == 1

    def test_list_conversations_empty(self, storage):
        """Test listing conversations when none exist."""
        result = storage.list_conversations()
        assert result == []

    def test_list_conversations(self, storage, sample_messages):
        """Test listing conversations."""
        storage.save_conversation(
            platform="chatgpt",
            session_id="session-1",
            messages=sample_messages,
            metadata={"title": "Chat 1"},
        )
        storage.save_conversation(
            platform="claude",
            session_id="session-2",
            messages=sample_messages,
            metadata={"title": "Chat 2"},
        )

        result = storage.list_conversations()

        assert len(result) == 2
        platforms = [r.platform for r in result]
        assert "chatgpt" in platforms
        assert "claude" in platforms

    def test_list_conversations_filter_by_platform(self, storage, sample_messages):
        """Test filtering conversations by platform."""
        storage.save_conversation(
            platform="chatgpt",
            session_id="session-1",
            messages=sample_messages,
            metadata={},
        )
        storage.save_conversation(
            platform="claude",
            session_id="session-2",
            messages=sample_messages,
            metadata={},
        )

        result = storage.list_conversations(platform="chatgpt")

        assert len(result) == 1
        assert result[0].platform == "chatgpt"

    def test_get_conversation(self, storage, sample_messages):
        """Test retrieving a conversation."""
        storage.save_conversation(
            platform="test-platform",
            session_id="session-001",
            messages=sample_messages,
            metadata={"title": "Test"},
        )

        result = storage.get_conversation("test-platform", "session-001")

        assert result is not None
        metadata, messages = result
        assert metadata.title == "Test"
        assert len(messages) == 2

    def test_get_conversation_not_found(self, storage):
        """Test retrieving a non-existent conversation."""
        result = storage.get_conversation("test-platform", "nonexistent")
        assert result is None

    def test_save_blob(self, storage):
        """Test saving a blob file."""
        content = b"test file content"
        file_hash = storage.save_blob("test-platform", content, "test.txt")

        assert file_hash is not None
        assert len(file_hash) == 64  # SHA-256 hash

        # Check file was saved
        blob_dir = storage.blobs_dir / "test-platform" / file_hash[:2] / file_hash[2:4]
        blob_path = blob_dir / f"{file_hash}.txt"
        assert blob_path.exists()

    def test_search(self, storage, sample_messages):
        """Test searching conversations."""
        storage.save_conversation(
            platform="test-platform",
            session_id="session-001",
            messages=sample_messages,
            metadata={},
        )

        results = storage.search("Hello")
        assert len(results) == 1

        results = storage.search("nonexistent")
        assert len(results) == 0

    def test_get_stats(self, storage, sample_messages):
        """Test getting storage statistics."""
        storage.save_conversation(
            platform="test-platform",
            session_id="session-001",
            messages=sample_messages,
            metadata={},
        )

        total_conversations, total_messages = storage.get_stats()

        assert total_conversations == 1
        assert total_messages == 2

"""Tests for talk-memory server."""
import pytest
from datetime import datetime
from pathlib import Path
import tempfile

from talk_memory_server.storage import Storage
from talk_memory_server.models import Message


@pytest.fixture
def temp_storage():
    """Create a temporary storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Storage(base_path=Path(tmpdir))


def test_save_conversation(temp_storage):
    """Test saving a conversation."""
    messages = [
        Message(
            uuid="msg-1",
            role="user",
            content="Hello",
            timestamp=datetime.now(),
        ),
        Message(
            uuid="msg-2",
            parent_uuid="msg-1",
            role="assistant",
            content="Hi there!",
            timestamp=datetime.now(),
        ),
    ]

    temp_storage.save_conversation(
        platform="test",
        session_id="sess-1",
        messages=messages,
        metadata={"title": "Test Conversation"},
    )

    result = temp_storage.get_conversation("test", "sess-1")
    assert result is not None
    metadata, msgs = result
    assert metadata.title == "Test Conversation"
    assert len(msgs) == 2


def test_list_conversations(temp_storage):
    """Test listing conversations."""
    messages = [
        Message(
            uuid="msg-1",
            role="user",
            content="Hello",
            timestamp=datetime.now(),
        ),
    ]

    temp_storage.save_conversation(
        platform="chatgpt",
        session_id="sess-1",
        messages=messages,
        metadata={"title": "First"},
    )

    temp_storage.save_conversation(
        platform="gemini",
        session_id="sess-2",
        messages=messages,
        metadata={"title": "Second"},
    )

    all_convs = temp_storage.list_conversations()
    assert len(all_convs) == 2

    chatgpt_convs = temp_storage.list_conversations(platform="chatgpt")
    assert len(chatgpt_convs) == 1
    assert chatgpt_convs[0].platform == "chatgpt"


def test_search_conversations(temp_storage):
    """Test searching conversations."""
    messages = [
        Message(
            uuid="msg-1",
            role="user",
            content="How do I deploy to Kubernetes?",
            timestamp=datetime.now(),
        ),
        Message(
            uuid="msg-2",
            role="assistant",
            content="You can use kubectl apply -f deployment.yaml",
            timestamp=datetime.now(),
        ),
    ]

    temp_storage.save_conversation(
        platform="chatgpt",
        session_id="sess-1",
        messages=messages,
        metadata={"title": "K8s Deployment"},
    )

    results = temp_storage.search("kubernetes")
    assert len(results) == 1
    assert "kubernetes" in results[0].matched_message.lower()


def test_save_blob(temp_storage):
    """Test saving a blob."""
    data = b"Hello, World!"
    file_hash = temp_storage.save_blob("test", data, "hello.txt")

    import hashlib
    expected_hash = hashlib.sha256(data).hexdigest()
    assert file_hash == expected_hash

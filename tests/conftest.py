"""Pytest configuration and fixtures."""
import os
import tempfile
from pathlib import Path

import pytest

from memory_talk.storage import Storage


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(temp_dir):
    """Create a Storage instance with temporary directory."""
    return Storage(base_path=temp_dir)


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    pytest.skip("Integration tests require httpx<0.28 with starlette TestClient")


@pytest.fixture
def sample_messages():
    """Sample messages for testing."""
    from datetime import datetime
    from memory_talk.models import Message, Attachment

    return [
        Message(
            uuid="msg-001",
            role="user",
            content="Hello, how are you?",
            timestamp=datetime.now(),
        ),
        Message(
            uuid="msg-002",
            role="assistant",
            content="I'm doing well, thank you!",
            timestamp=datetime.now(),
        ),
    ]


@pytest.fixture
def sample_conversation():
    """Sample conversation data for testing."""
    from datetime import datetime
    from memory_talk.models import Message, Participant

    return {
        "platform": "test-platform",
        "session_id": "test-session-001",
        "messages": [
            Message(
                uuid="msg-001",
                role="user",
                content="Hello",
                timestamp=datetime.now(),
            ),
            Message(
                uuid="msg-002",
                role="assistant",
                content="Hi there!",
                timestamp=datetime.now(),
            ),
        ],
        "metadata": {
            "title": "Test Conversation",
            "participants": [
                Participant(name="User", role="user"),
                Participant(name="Assistant", role="assistant"),
            ],
        },
    }

"""Integration tests for API endpoints."""
from datetime import datetime

import pytest

from memory_talk.models import Message


@pytest.mark.integration
class TestHealthEndpoint:
    """Test cases for health check endpoint."""

    def test_health_check(self, client):
        """Test health endpoint returns ok."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.integration
class TestIngestEndpoint:
    """Test cases for /api/ingest endpoint."""

    def test_ingest_conversation(self, client, sample_conversation):
        """Test ingesting a conversation."""
        response = client.post("/api/ingest", json=sample_conversation)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["session_id"] == "test-session-001"

    def test_ingest_with_dict_messages(self, client):
        """Test ingesting conversation with dict messages."""
        data = {
            "platform": "test-platform",
            "session_id": "session-dict",
            "messages": [
                {
                    "uuid": "msg-001",
                    "role": "user",
                    "content": "Hello",
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "metadata": {"title": "Dict Test"},
        }

        response = client.post("/api/ingest", json=data)
        assert response.status_code == 200


@pytest.mark.integration
class TestConversationsEndpoint:
    """Test cases for /api/conversations endpoints."""

    def test_list_conversations_empty(self, client):
        """Test listing conversations when none exist."""
        response = client.get("/api/conversations")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_conversations(self, client, sample_conversation):
        """Test listing conversations after ingest."""
        # First ingest a conversation
        client.post("/api/ingest", json=sample_conversation)

        # Then list
        response = client.get("/api/conversations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "test-session-001"

    def test_list_conversations_filter_platform(self, client, sample_conversation):
        """Test filtering conversations by platform."""
        client.post("/api/ingest", json=sample_conversation)

        response = client.get("/api/conversations?platform=test-platform")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        response = client.get("/api/conversations?platform=nonexistent")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_conversation(self, client, sample_conversation):
        """Test getting a specific conversation."""
        # First ingest
        client.post("/api/ingest", json=sample_conversation)

        # Then get
        response = client.get("/api/conversations/test-platform/test-session-001")
        assert response.status_code == 200
        data = response.json()
        assert "metadata" in data
        assert "messages" in data

    def test_get_conversation_not_found(self, client):
        """Test getting a non-existent conversation."""
        response = client.get("/api/conversations/nonexistent/session")
        assert response.status_code == 404


@pytest.mark.integration
class TestSearchEndpoint:
    """Test cases for /api/search endpoint."""

    def test_search_empty(self, client):
        """Test search with no conversations."""
        response = client.get("/api/search?q=test")
        assert response.status_code == 200
        assert response.json() == []

    def test_search_with_results(self, client, sample_conversation):
        """Test search returns results."""
        # Ingest conversation with known content
        client.post("/api/ingest", json=sample_conversation)

        response = client.get("/api/search?q=Hello")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_search_no_results(self, client, sample_conversation):
        """Test search with no matching results."""
        client.post("/api/ingest", json=sample_conversation)

        response = client.get("/api/search?q=xyznonexistent")
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.integration
class TestStatusEndpoint:
    """Test cases for status endpoints."""

    def test_get_status(self, client):
        """Test getting server status."""
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()

        assert "version" in data
        assert "total_conversations" in data
        assert "total_messages" in data
        assert "sources" in data

    def test_get_sources(self, client):
        """Test getting sources list."""
        response = client.get("/api/sources")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

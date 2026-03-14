"""Integration tests for Claude Code data import."""
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest
import requests


# Patch Storage to support environment variable for base_path
_original_storage_init = None


def _get_test_base_path():
    """Get test base path from environment variable."""
    return os.environ.get("MEMORY_TALK_TEST_DATA_DIR")


def wait_for_server(url: str, timeout: int = 30) -> bool:
    """Wait for server to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


@pytest.mark.integration
class TestClaudeCodeImport:
    """Test cases for Claude Code data import."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Set up test environment with temporary server."""
        # Create temporary directory for database
        self.temp_dir = tmp_path / "memory_talk_test"
        self.temp_dir.mkdir(exist_ok=True)
        self.port = 18788  # Use a unique port
        self.base_url = f"http://localhost:{self.port}"

        # Set environment variable for data directory
        test_env = os.environ.copy()
        test_env["MEMORY_TALK_DATA_DIR"] = str(self.temp_dir)

        # Get the project root
        project_root = Path(__file__).parent.parent.parent

        # Start server process using uvicorn directly
        self.server_process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "memory_talk.server:app",
                "--host", "localhost",
                "--port", str(self.port),
            ],
            env=test_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(project_root),
        )

        # Wait for server to be ready
        assert wait_for_server(f"{self.base_url}/health", timeout=30), "Server failed to start"

        yield

        # Cleanup
        if self.server_process.poll() is None:
            self.server_process.send_signal(signal.SIGTERM)
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()

    def _get(self, path: str) -> requests.Response:
        """Make GET request."""
        return requests.get(f"{self.base_url}{path}", timeout=10)

    def _post(self, path: str, json: dict) -> requests.Response:
        """Make POST request."""
        return requests.post(f"{self.base_url}{path}", json=json, timeout=10)

    @pytest.fixture
    def claude_code_data(self):
        """Claude Code format test data matching export_sessions.py output."""
        base_time = datetime(2025, 1, 15, 10, 0, 0)
        return {
            "platform": "claude-code",
            "session_id": "test-project-2025-01-15",
            "messages": [
                {
                    "uuid": "msg-001",
                    "parent_uuid": None,
                    "role": "user",
                    "content": "Hello, help me with my Python project",
                    "timestamp": (base_time).isoformat(),
                },
                {
                    "uuid": "msg-002",
                    "parent_uuid": "msg-001",
                    "role": "assistant",
                    "content": "Of course! I'd be happy to help with your Python project. What would you like to work on?",
                    "timestamp": (base_time).isoformat(),
                },
                {
                    "uuid": "msg-003",
                    "parent_uuid": "msg-002",
                    "role": "user",
                    "content": "Can you create a simple web server?",
                    "timestamp": (base_time).isoformat(),
                },
                {
                    "uuid": "msg-004",
                    "parent_uuid": "msg-003",
                    "role": "assistant",
                    "content": "I'll create a simple Flask web server for you.",
                    "metadata": {"model": "claude-sonnet-4-20250514"},
                    "timestamp": (base_time).isoformat(),
                },
                {
                    "uuid": "msg-005",
                    "parent_uuid": "msg-004",
                    "role": "assistant",
                    "content": "[tool_use: Read]",
                    "metadata": {"tool_name": "Read"},
                    "timestamp": (base_time).isoformat(),
                },
                {
                    "uuid": "msg-006",
                    "parent_uuid": "msg-005",
                    "role": "assistant",
                    "content": "[tool_use: Write]",
                    "metadata": {"tool_name": "Write"},
                    "timestamp": (base_time).isoformat(),
                },
                {
                    "uuid": "msg-007",
                    "parent_uuid": "msg-006",
                    "role": "assistant",
                    "content": "I've created a simple Flask web server in app.py. Here's what it does:\n\n- Routes for / and /hello\n- Basic request handling",
                    "metadata": {"model": "claude-sonnet-4-20250514"},
                    "timestamp": (base_time).isoformat(),
                },
                {
                    "uuid": "msg-008",
                    "parent_uuid": "msg-007",
                    "role": "user",
                    "content": "Thanks! Can you add a /goodbye route?",
                    "timestamp": (base_time).isoformat(),
                },
            ],
            "metadata": {
                "title": "Claude Code - /home/user/my-python-project",
                "project_path": "/home/user/my-python-project",
            },
        }

    def test_import_claude_code_conversation(self, claude_code_data):
        """Test importing a Claude Code conversation."""
        response = self._post("/api/ingest", claude_code_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["session_id"] == "test-project-2025-01-15"

    def test_list_claude_code_conversations(self, claude_code_data):
        """Test listing Claude Code conversations."""
        # Import first
        self._post("/api/ingest", claude_code_data)

        # List all conversations
        response = self._get("/api/conversations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "test-project-2025-01-15"
        assert data[0]["platform"] == "claude-code"

        # Filter by platform
        response = self._get("/api/conversations?platform=claude-code")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        # Filter by non-existent platform
        response = self._get("/api/conversations?platform=nonexistent")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_conversation_details(self, claude_code_data):
        """Test getting conversation details via /api/messages."""
        # Import first
        self._post("/api/ingest", claude_code_data)

        # Get messages with platform and session_id filters
        response = self._get("/api/messages?platform=claude-code&session_id=test-project-2025-01-15")
        assert response.status_code == 200
        data = response.json()

        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "messages" in data
        assert data["total"] == 8
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert len(data["messages"]) == 8

        # Verify message content
        messages = data["messages"]
        assert messages[0]["content"] == "Hello, help me with my Python project"
        assert messages[0]["role"] == "user"

    def test_subject_matching(self, claude_code_data):
        """Test that subjects are correctly matched for messages."""
        # Import first
        self._post("/api/ingest", claude_code_data)

        # Get messages
        response = self._get("/api/messages?platform=claude-code&session_id=test-project-2025-01-15")
        assert response.status_code == 200
        data = response.json()
        messages = data["messages"]

        # Verify subject_id matching
        # user messages should have subject_id = "human-default"
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert all(m["subject_id"] == "human-default" for m in user_msgs)

        # assistant with model should have subject_id = "ai-{model}"
        assistant_with_model = [m for m in messages if m.get("metadata", {}).get("model")]
        for msg in assistant_with_model:
            expected = f"ai-{msg['metadata']['model'].replace(' ', '-').replace('.', '-').lower()}"
            assert msg["subject_id"] == expected

        # assistant with tool_name should have subject_id = "tool-{tool_name}"
        assistant_with_tool = [
            m for m in messages
            if m["role"] == "assistant" and m.get("metadata", {}).get("tool_name")
        ]
        for msg in assistant_with_tool:
            expected = f"tool-{msg['metadata']['tool_name']}"
            assert msg["subject_id"] == expected

        # assistant without model or tool should have default subject_id
        assistant_default = [
            m for m in messages
            if m["role"] == "assistant"
            and not m.get("metadata", {}).get("model")
            and not m.get("metadata", {}).get("tool_name")
        ]
        assert all(m["subject_id"] == "ai-assistant" for m in assistant_default)

    def test_subject_creation(self, claude_code_data):
        """Test that subjects are automatically created."""
        # Import first
        self._post("/api/ingest", claude_code_data)

        # Get subjects list
        response = self._get("/api/subjects")
        assert response.status_code == 200
        subjects = response.json()

        # Verify default subjects exist
        subject_ids = [s["id"] for s in subjects]
        assert "human-default" in subject_ids
        assert "ai-assistant" in subject_ids

        # Verify AI model subjects are created
        model_subjects = [s for s in subjects if s["id"].startswith("ai-")]
        assert len(model_subjects) >= 1  # At least one AI model subject

        # Verify tool subjects are created
        tool_subjects = [s for s in subjects if s["id"].startswith("tool-")]
        assert len(tool_subjects) >= 2  # At least Read and Write tools

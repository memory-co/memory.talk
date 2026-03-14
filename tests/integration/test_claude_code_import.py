"""Integration tests for Claude Code data import."""
import importlib.util
import json
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


# Load connector's parse_messages function dynamically
def _load_parse_messages():
    """Load parse_messages from connector script."""
    project_root = Path(__file__).parent.parent.parent
    script_path = project_root / "connectors" / "claude-code" / "export_sessions.py"
    spec = importlib.util.spec_from_file_location("export_sessions", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_messages


parse_messages = _load_parse_messages()


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
    def claude_code_data(self, tmp_path):
        """Claude Code format test data using connector's parse_messages logic."""
        # Create a temporary JSONL file with Claude Code session data
        session_file = tmp_path / "test-project-2025-01-15.jsonl"

        base_time = datetime(2025, 1, 15, 10, 0, 0)
        jsonl_data = [
            {
                "uuid": "msg-001",
                "parentUuid": None,
                "type": "user",
                "message": {"content": "Hello, help me with my Python project"},
                "timestamp": base_time.isoformat(),
            },
            {
                "uuid": "msg-002",
                "parentUuid": "msg-001",
                "type": "assistant",
                "message": {"content": [
                    {"type": "text", "text": "Of course! I'd be happy to help with your Python project. What would you like to work on?"}
                ]},
                "timestamp": base_time.isoformat(),
            },
            {
                "uuid": "msg-003",
                "parentUuid": "msg-002",
                "type": "user",
                "message": {"content": "Can you create a simple web server?"},
                "timestamp": base_time.isoformat(),
            },
            {
                "uuid": "msg-004",
                "parentUuid": "msg-003",
                "type": "assistant",
                "message": {"content": [
                    {"type": "text", "text": "I'll create a simple Flask web server for you."}
                ], "model": "claude-sonnet-4-20250514"},
                "timestamp": base_time.isoformat(),
            },
            {
                "uuid": "msg-005",
                "parentUuid": "msg-004",
                "type": "assistant",
                "message": {"content": [
                    {"type": "tool_use", "name": "Read", "input": {}}
                ]},
                "timestamp": base_time.isoformat(),
            },
            {
                "uuid": "msg-006",
                "parentUuid": "msg-005",
                "type": "assistant",
                "message": {"content": [
                    {"type": "tool_use", "name": "Write", "input": {}}
                ]},
                "timestamp": base_time.isoformat(),
            },
            {
                "uuid": "msg-007",
                "parentUuid": "msg-006",
                "type": "assistant",
                "message": {"content": [
                    {"type": "text", "text": "I've created a simple Flask web server in app.py."}
                ], "model": "claude-sonnet-4-20250514"},
                "timestamp": base_time.isoformat(),
            },
            {
                "uuid": "msg-008",
                "parentUuid": "msg-007",
                "type": "user",
                "message": {"content": "Thanks! Can you add a /goodbye route?"},
                "timestamp": base_time.isoformat(),
            },
        ]

        with open(session_file, "w") as f:
            for item in jsonl_data:
                f.write(json.dumps(item) + "\n")

        # Use connector's parse_messages to generate test data
        messages = parse_messages(session_file)

        return {
            "platform": "claude-code",
            "conversation_id": "test-project-2025-01-15",
            "messages": messages,
            "metadata": {
                "title": "Claude Code - /home/user/my-python-project",
                "project_path": "/home/user/my-python-project",
            },
        }

    def test_import_claude_code_conversation(self, claude_code_data):
        """Test importing a Claude Code conversation."""
        response = self._post("/api/v1/ingest", claude_code_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["conversation_id"] == "test-project-2025-01-15"

    def test_list_claude_code_conversations(self, claude_code_data):
        """Test listing Claude Code conversations."""
        # Import first
        self._post("/api/v1/ingest", claude_code_data)

        # List all conversations
        response = self._get("/api/v1/conversations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["conversation_id"] == "test-project-2025-01-15"
        assert data[0]["platform"] == "claude-code"

        # Filter by platform
        response = self._get("/api/v1/conversations?platform=claude-code")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        # Filter by non-existent platform
        response = self._get("/api/v1/conversations?platform=nonexistent")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_conversation_details(self, claude_code_data):
        """Test getting conversation details via /api/v1/messages."""
        # Import first
        self._post("/api/v1/ingest", claude_code_data)

        # Get messages with platform and conversation_id filters
        response = self._get("/api/v1/messages?platform=claude-code&conversation_id=test-project-2025-01-15")
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
        """Test that subject_ids are correctly set for messages based on role."""
        # Import first
        self._post("/api/v1/ingest", claude_code_data)

        # Get messages
        response = self._get("/api/v1/messages?platform=claude-code&conversation_id=test-project-2025-01-15")
        assert response.status_code == 200
        data = response.json()
        messages = data["messages"]

        # Verify subject_id based on role (set by connector)
        # user messages should have subject_id = "human-default"
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert all(m["subject_id"] == "human-default" for m in user_msgs)

        # assistant messages should have subject_id = "ai-assistant"
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert all(m["subject_id"] == "ai-assistant" for m in assistant_msgs)

    def test_subject_creation(self, claude_code_data):
        """Test that default subjects are created."""
        # Import first
        self._post("/api/v1/ingest", claude_code_data)

        # Get subjects list
        response = self._get("/api/v1/subjects")
        assert response.status_code == 200
        subjects = response.json()

        # Verify default subjects exist
        subject_ids = [s["id"] for s in subjects]
        assert "human-default" in subject_ids
        assert "ai-assistant" in subject_ids

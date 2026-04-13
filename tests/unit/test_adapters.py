"""Unit tests for adapters."""

import json

import pytest

from memory_talk.adapters.claude_code import ClaudeCodeAdapter
from memory_talk.adapters.registry import get_adapter


class TestClaudeCodeAdapter:
    @pytest.fixture
    def adapter(self, temp_dir):
        return ClaudeCodeAdapter(projects_dir=temp_dir)

    @pytest.fixture
    def session_file(self, temp_dir):
        project_dir = temp_dir / "-home-testuser-myproject"
        project_dir.mkdir(parents=True)
        session_path = project_dir / "abc123.jsonl"
        lines = [
            json.dumps({
                "type": "user",
                "uuid": "u1",
                "timestamp": "2026-04-10T14:30:00Z",
                "message": {"content": "Hello, help me with Python"},
            }),
            json.dumps({
                "type": "assistant",
                "uuid": "a1",
                "timestamp": "2026-04-10T14:30:05Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "Sure, what do you need?"},
                    ]
                },
            }),
            json.dumps({
                "type": "assistant",
                "uuid": "a2",
                "timestamp": "2026-04-10T14:31:00Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "Let me check"},
                        {"type": "tool_use", "name": "bash", "input": {"command": "ls"}},
                        {"type": "tool_result", "content": "file.py"},
                    ]
                },
            }),
        ]
        session_path.write_text("\n".join(lines) + "\n")
        return session_path

    def test_discover(self, adapter, session_file):
        paths = adapter.discover()
        assert len(paths) == 1
        assert paths[0].stem == "abc123"

    def test_discover_empty(self, adapter):
        assert adapter.discover() == []

    def test_convert(self, adapter, session_file):
        session = adapter.convert(session_file)
        assert session.session_id == "abc123"
        assert session.source == "claude-code"
        assert len(session.rounds) == 3

    def test_convert_user_round(self, adapter, session_file):
        session = adapter.convert(session_file)
        r = session.rounds[0]
        assert r.speaker == "user"
        assert r.role == "human"
        assert len(r.content) == 1
        assert r.content[0].type == "text"
        assert "Python" in r.content[0].text

    def test_convert_assistant_round(self, adapter, session_file):
        session = adapter.convert(session_file)
        r = session.rounds[1]
        assert r.speaker == "assistant"
        assert r.role == "assistant"
        assert r.content[0].text == "Sure, what do you need?"

    def test_convert_tool_use(self, adapter, session_file):
        session = adapter.convert(session_file)
        r = session.rounds[2]
        assert len(r.content) == 3
        assert r.content[0].type == "text"
        assert r.content[1].type == "tool_use"
        assert r.content[1].name == "bash"
        assert r.content[2].type == "tool_result"

    def test_convert_metadata(self, adapter, session_file):
        session = adapter.convert(session_file)
        assert "project" in session.metadata
        assert session.created_at is not None

    def test_convert_skips_non_message_lines(self, adapter, temp_dir):
        project_dir = temp_dir / "testproj"
        project_dir.mkdir()
        path = project_dir / "sess1.jsonl"
        lines = [
            json.dumps({"type": "system", "message": "init"}),
            json.dumps({"type": "user", "uuid": "u1", "message": {"content": "hi"}}),
            "not valid json",
            "",
        ]
        path.write_text("\n".join(lines) + "\n")
        session = adapter.convert(path)
        assert len(session.rounds) == 1


class TestRegistry:
    def test_get_known_adapter(self):
        adapter = get_adapter("claude-code")
        assert adapter.name == "claude-code"

    def test_get_unknown_adapter(self):
        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("nonexistent")

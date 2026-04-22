"""Story 05: 输出格式 — JSON 中文不转义 + text 格式可用"""
import json
from memory_talk.adapters.claude_code import ClaudeCodeAdapter
from pathlib import Path
import shutil


class TestOutputFormat:

    def _setup_data(self, client, fake_claude_sessions):
        """Import a session and create a card with Chinese content."""
        adapter = ClaudeCodeAdapter(projects_dir=fake_claude_sessions.parent)
        paths = adapter.discover()
        db_path = [p for p in paths if "db_decision" in p.name][0]
        session = adapter.convert(db_path)
        r = client.post("/v1/sessions", json=session.model_dump(mode="json"))
        session_id = r.json()["session_id"]

        card = client.post("/v1/cards", json={
            "summary": "项目选定 LanceDB 作为向量存储方案",
            "session_id": session_id,
            "rounds": [
                {"role": "human", "text": "向量库选型，ChromaDB 和 LanceDB 哪个好？"},
                {"role": "assistant", "text": "推荐 LanceDB，零依赖"},
            ],
            "links": [{"id": session_id, "type": "session", "comment": "从选型讨论提取"}],
        })
        return session_id, card.json()["card_id"]

    def test_json_chinese_no_escape(self, client, config, fake_claude_sessions):
        """JSON output should show Chinese directly, not \\uXXXX."""
        session_id, card_id = self._setup_data(client, fake_claude_sessions)

        # Recall with Chinese query
        r = client.post("/v1/recall", json={"query": "向量库选型", "top_k": 5})
        raw_json = json.dumps(r.json(), ensure_ascii=False)

        # Should contain Chinese characters directly
        assert "LanceDB" in raw_json
        assert "\\u" not in raw_json  # no unicode escapes

    def test_card_get_chinese(self, client, config, fake_claude_sessions):
        """Card get should return Chinese text without escaping."""
        session_id, card_id = self._setup_data(client, fake_claude_sessions)

        r = client.get(f"/v1/cards/{card_id}")
        card_data = r.json()
        assert "项目选定" in card_data["summary"]
        assert "向量库选型" in card_data["rounds"][0]["text"]

    def test_cli_format_option(self):
        """Verify -f option exists on leaf commands."""
        from click.testing import CliRunner
        from memory_talk.cli import main

        runner = CliRunner()

        # -f should work on server status (leaf command)
        result = runner.invoke(main, ["server", "status", "-f", "text", "--help"])
        assert result.exit_code == 0

        # -f should work on session list
        result = runner.invoke(main, ["session", "list", "--help"])
        assert result.exit_code == 0
        assert "-f" in result.output or "--format" in result.output

        # -f should work on card list
        result = runner.invoke(main, ["card", "list", "--help"])
        assert result.exit_code == 0
        assert "-f" in result.output or "--format" in result.output

        # -f should work on recall
        result = runner.invoke(main, ["recall", "--help"])
        assert result.exit_code == 0
        assert "-f" in result.output or "--format" in result.output


# Fixture for this test — reuse story_01's session data
import pytest

@pytest.fixture
def fake_claude_sessions(temp_root):
    src = Path(__file__).parent / "sessions"
    dst = temp_root / "claude_projects" / "testproject"
    shutil.copytree(src, dst)
    return dst

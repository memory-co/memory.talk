"""End-to-end integration test: explore → cards create → recall."""

import json

import pytest
from click.testing import CliRunner

from memory_talk.cli import main


@pytest.fixture
def runner(temp_dir):
    return CliRunner(), str(temp_dir)


class TestPipeline:
    def test_setup(self, runner):
        cli_runner, data_root = runner
        result = cli_runner.invoke(main, ["setup", "--data-root", data_root, "--embedding", "dummy"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

    def test_full_pipeline(self, runner, temp_dir):
        cli_runner, data_root = runner

        # 1. Setup
        result = cli_runner.invoke(main, ["setup", "--data-root", data_root, "--embedding", "dummy"])
        assert result.exit_code == 0

        # 2. Create a fake session file to ingest
        project_dir = temp_dir / "fake_claude" / "testproject"
        project_dir.mkdir(parents=True)
        session_file = project_dir / "sess001.jsonl"
        lines = [
            json.dumps({"type": "user", "uuid": "u1", "timestamp": "2026-04-10T10:00:00Z",
                        "message": {"content": "What database should we use?"}}),
            json.dumps({"type": "assistant", "uuid": "a1", "timestamp": "2026-04-10T10:00:05Z",
                        "message": {"content": [{"type": "text", "text": "I recommend LanceDB for vector storage."}]}}),
        ]
        session_file.write_text("\n".join(lines) + "\n")

        # 3. Ingest
        result = cli_runner.invoke(main, ["explore", "ingest", str(session_file), "--data-root", data_root])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        session_id = data["session_id"]

        # 4. List unbuilt sessions
        result = cli_runner.invoke(main, ["sessions", "list", "--unbuilt", "--data-root", data_root])
        assert result.exit_code == 0
        sessions = json.loads(result.output)
        assert len(sessions) == 1

        # 5. Read session rounds
        result = cli_runner.invoke(main, ["sessions", "read", session_id, "--data-root", data_root])
        assert result.exit_code == 0
        rounds = json.loads(result.output)
        assert len(rounds) == 2

        # 6. Create a Talk-Card (simulating what LLM would do in /build)
        card_data = json.dumps({
            "cognition_summary": "Decided to use LanceDB for vector storage due to zero-dependency local operation",
            "compressed_rounds": "User asked about database selection. Recommended LanceDB for vector storage.",
            "session_id": session_id,
            "round_start": 0,
            "round_end": 2,
        })
        result = cli_runner.invoke(main, ["cards", "create", card_data, "--data-root", data_root])
        assert result.exit_code == 0
        card_result = json.loads(result.output)
        assert card_result["status"] == "ok"
        card_id = card_result["card_id"]

        # 7. Mark session as built
        result = cli_runner.invoke(main, ["sessions", "mark-built", session_id, "--data-root", data_root])
        assert result.exit_code == 0

        # 8. Verify no more unbuilt
        result = cli_runner.invoke(main, ["sessions", "list", "--unbuilt", "--data-root", data_root])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

        # 9. Recall
        result = cli_runner.invoke(main, ["recall", "database selection", "--data-root", data_root])
        assert result.exit_code == 0
        recall_data = json.loads(result.output)
        assert recall_data["count"] >= 1
        assert "LanceDB" in recall_data["results"][0]["cognition_summary"]

        # 10. Get card
        result = cli_runner.invoke(main, ["cards", "get", card_id, "--data-root", data_root])
        assert result.exit_code == 0

        # 11. Status
        result = cli_runner.invoke(main, ["status", "--data-root", data_root])
        assert result.exit_code == 0
        status = json.loads(result.output)
        assert status["sessions_total"] == 1
        assert status["cards_total"] == 1

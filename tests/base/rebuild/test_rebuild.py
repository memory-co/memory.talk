"""Test rebuild: delete SQLite, rebuild from files, verify data restored."""
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from memory_talk.adapters.claude_code import ClaudeCodeAdapter
from memory_talk.api import create_app
from memory_talk.config import Config
from memory_talk.service.rebuild import rebuild_sync
from tests.conftest import load_sessions_from_dir

SESSIONS_DIR = Path(__file__).parent / "sessions"


@pytest.fixture
def fake_claude_sessions(temp_root):
    src = Path(__file__).parent.parent.parent / "scenario" / "01_database_decision" / "sessions"
    dst = temp_root / "claude_projects" / "testproject"
    shutil.copytree(src, dst)
    return dst


class TestRebuild:
    def test_rebuild_restores_sessions_and_cards(self, client, config, fake_claude_sessions):
        # 1. Import a session and create a card
        adapter = ClaudeCodeAdapter(projects_dir=fake_claude_sessions.parent)
        for path in adapter.discover():
            session = adapter.convert(path)
            client.post("/sessions", json=session.model_dump(mode="json"))

        sessions_before = client.get("/sessions").json()
        assert len(sessions_before) >= 1
        session_id = sessions_before[0]["session_id"]

        client.post("/cards", json={
            "summary": "选定 LanceDB",
            "session_id": session_id,
            "rounds": [{"role": "human", "text": "test"}],
            "links": [{"id": session_id, "type": "session"}],
        })

        cards_before = client.get("/cards").json()
        assert len(cards_before) >= 1

        # 2. Delete SQLite
        config.db_path.unlink()

        # 3. Rebuild (sync for test)
        result = rebuild_sync(config)
        assert result["status"] == "ok"
        assert result["sessions"] >= 1
        assert result["cards"] >= 1

        # 4. Recreate client with rebuilt db
        app = create_app(config)
        with TestClient(app) as new_client:
            sessions_after = new_client.get("/sessions").json()
            assert len(sessions_after) == len(sessions_before)

            cards_after = new_client.get("/cards").json()
            assert len(cards_after) == len(cards_before)

            # Recall should work (LanceDB rebuilt)
            recall = new_client.post("/recall", json={"query": "LanceDB", "top_k": 5}).json()
            assert recall["count"] >= 1

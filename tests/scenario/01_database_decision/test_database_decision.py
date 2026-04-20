"""Story 01: 数据库选型的记忆"""
import shutil
from pathlib import Path

import pytest

from memory_talk.adapters.claude_code import ClaudeCodeAdapter
from tests.conftest import load_sessions_from_dir

SESSIONS_DIR = Path(__file__).parent / "sessions"


@pytest.fixture
def fake_claude_sessions(temp_root):
    """Copy session JSONL files into a fake Claude projects directory."""
    projects = temp_root / "claude_projects" / "testproject"
    projects.mkdir(parents=True)
    for src in load_sessions_from_dir(SESSIONS_DIR):
        shutil.copy2(src, projects / src.name)
    return projects


class TestDatabaseDecision:
    def test_full_story(self, client, config, fake_claude_sessions):
        # 1. Import session
        adapter = ClaudeCodeAdapter(projects_dir=fake_claude_sessions.parent)
        paths = adapter.discover()
        db_path = [p for p in paths if "db_decision" in p.name][0]
        session = adapter.convert(db_path)
        r = client.post("/v1/sessions", json=session.model_dump(mode="json"))
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        session_id = r.json()["session_id"]

        # 2. List sessions
        r = client.get("/v1/sessions")
        assert r.status_code == 200
        assert any(s["session_id"] == session_id for s in r.json())

        # 3. Read rounds
        r = client.get(f"/v1/sessions/{session_id}")
        assert r.status_code == 200
        assert len(r.json()) == 3

        # 4. Create card
        r = client.post("/v1/cards", json={
            "summary": "项目选定 LanceDB 作为向量存储方案",
            "session_id": session_id,
            "rounds": [
                {"role": "human", "text": "ChromaDB 和 LanceDB 哪个好？"},
                {"role": "assistant", "text": "LanceDB 零依赖嵌入式", "thinking": "部署形态是关键"},
                {"role": "human", "text": "就用 LanceDB"},
            ],
            "links": [{"id": session_id, "type": "session", "comment": "从选型讨论提取"}],
        })
        assert r.status_code == 200
        card_id = r.json()["card_id"]

        # 5. Recall
        r = client.post("/v1/recall", json={"query": "数据库选型 LanceDB", "top_k": 5})
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 1
        found = [c for c in data["results"] if c["card_id"] == card_id]
        assert len(found) == 1
        assert found[0]["ttl"] > 0
        assert len(found[0]["links"]) >= 1

        # 6. Status
        r = client.get("/v1/status")
        assert r.status_code == 200
        assert r.json()["sessions_total"] >= 1
        assert r.json()["cards_total"] >= 1

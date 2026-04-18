"""Story 03: 一次意外的回忆 — recall + TTL"""
import shutil
import time
from pathlib import Path

import pytest

from memory_talk.adapters.claude_code import ClaudeCodeAdapter
from tests.conftest import load_sessions_from_dir

DB_SESSIONS_DIR = Path(__file__).parent.parent / "story_01_database" / "sessions"
BUG_SESSIONS_DIR = Path(__file__).parent.parent / "story_02_bug" / "sessions"


@pytest.fixture
def fake_claude_sessions(temp_root):
    """Copy session JSONL files from story_01 and story_02 into a fake Claude projects directory."""
    projects = temp_root / "claude_projects" / "testproject"
    projects.mkdir(parents=True)
    for src in load_sessions_from_dir(DB_SESSIONS_DIR):
        shutil.copy2(src, projects / src.name)
    for src in load_sessions_from_dir(BUG_SESSIONS_DIR):
        shutil.copy2(src, projects / src.name)
    return projects


class TestRecallAndConnect:
    def test_full_story(self, client, config, fake_claude_sessions):
        # Setup: import + create cards
        adapter = ClaudeCodeAdapter(projects_dir=fake_claude_sessions.parent)
        for path in adapter.discover():
            session = adapter.convert(path)
            client.post("/sessions", json=session.model_dump(mode="json"))

        sessions = client.get("/sessions").json()
        db_sid = [s for s in sessions if "db_decision" in s["session_id"]][0]["session_id"]
        bug_sid = [s for s in sessions if "bug" in s["session_id"]][0]["session_id"]

        card1 = client.post("/cards", json={
            "summary": "选定 LanceDB 做向量存储 零依赖",
            "session_id": db_sid,
            "rounds": [{"role": "human", "text": "ChromaDB vs LanceDB"}, {"role": "assistant", "text": "LanceDB"}],
            "links": [{"id": db_sid, "type": "session"}],
        }).json()

        card2 = client.post("/cards", json={
            "summary": "LanceDB NFS 建表阻塞 预创建表",
            "session_id": bug_sid,
            "rounds": [{"role": "human", "text": "卡住"}, {"role": "assistant", "text": "NFS fsync"}],
            "links": [
                {"id": bug_sid, "type": "session"},
                {"id": card1["card_id"], "type": "card", "comment": "选型后果"},
            ],
        }).json()

        # 1. Recall
        recall = client.post("/recall", json={"query": "ChromaDB 选型 LanceDB", "top_k": 5}).json()
        assert recall["count"] >= 1

        # 2. Card TTL refreshed by recall
        card1_data = client.get(f"/cards/{card1['card_id']}").json()
        initial_ttl = card1_data["ttl"]

        time.sleep(0.1)
        client.post("/recall", json={"query": "LanceDB 向量存储", "top_k": 5})
        card1_after = client.get(f"/cards/{card1['card_id']}").json()
        assert card1_after["ttl"] >= initial_ttl

        # 3. Link TTL refreshed by cards get --link-id
        links = client.get("/links", params={"id": card2["card_id"]}).json()
        card_link = [lk for lk in links if lk.get("target_type") == "card"][0]
        link_id = card_link["link_id"]
        link_ttl_before = card_link["ttl"]

        time.sleep(0.1)
        client.get(f"/cards/{card2['card_id']}", params={"link_id": link_id})
        links_after = client.get("/links", params={"id": card2["card_id"]}).json()
        card_link_after = [lk for lk in links_after if lk["link_id"] == link_id][0]
        assert card_link_after["ttl"] >= link_ttl_before

        # 4. Status
        st = client.get("/status").json()
        assert st["sessions_total"] == 2
        assert st["cards_total"] == 2
        assert st["links_total"] >= 3

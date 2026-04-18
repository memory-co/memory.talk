"""Story 02: Bug 排查的记忆"""
from memory_talk.adapters.claude_code import ClaudeCodeAdapter

class TestBugInvestigation:
    def test_full_story(self, client, config, fake_claude_sessions):
        adapter = ClaudeCodeAdapter(projects_dir=fake_claude_sessions.parent)
        for path in adapter.discover():
            session = adapter.convert(path)
            client.post("/sessions", json=session.model_dump(mode="json"))

        sessions = client.get("/sessions").json()
        db_session = [s for s in sessions if "db_decision" in s["session_id"]][0]
        bug_session = [s for s in sessions if "bug" in s["session_id"]][0]

        # Card 1: database decision
        card1 = client.post("/cards", json={
            "summary": "选定 LanceDB 做向量存储",
            "session_id": db_session["session_id"],
            "rounds": [{"role": "human", "text": "ChromaDB vs LanceDB?"}, {"role": "assistant", "text": "用 LanceDB"}],
            "links": [{"id": db_session["session_id"], "type": "session"}],
        }).json()
        card1_id = card1["card_id"]

        # Card 2: bug with links to session AND card1
        card2 = client.post("/cards", json={
            "summary": "cards create 偶发卡死——LanceDB NFS 建表阻塞",
            "session_id": bug_session["session_id"],
            "rounds": [
                {"role": "human", "text": "cards create 卡住"},
                {"role": "assistant", "text": "NFS 上 fsync 慢", "thinking": "阻塞不是异常"},
                {"role": "assistant", "text": "预创建表结构"},
            ],
            "links": [
                {"id": bug_session["session_id"], "type": "session", "comment": "bug 排查"},
                {"id": card1_id, "type": "card", "comment": "选型后果"},
            ],
        }).json()
        card2_id = card2["card_id"]

        # Verify links
        links = client.get("/links", params={"id": card2_id}).json()
        assert len(links) == 2

        # Verify card
        card = client.get(f"/cards/{card2_id}").json()
        assert "NFS" in card["summary"]
        assert len(card["rounds"]) == 3
        assert card["ttl"] > 0

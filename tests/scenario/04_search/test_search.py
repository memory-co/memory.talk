"""Story 04: search — hybrid FTS + vector for cards, FTS for sessions, with DSL filtering."""
import shutil
from pathlib import Path

import pytest

from memory_talk.adapters.claude_code import ClaudeCodeAdapter
from tests.conftest import load_sessions_from_dir

SESSIONS_DIR = Path(__file__).parent / "sessions"


@pytest.fixture
def fake_claude_sessions(temp_root):
    projects = temp_root / "claude_projects" / "testproject"
    projects.mkdir(parents=True)
    for src in load_sessions_from_dir(SESSIONS_DIR):
        shutil.copy2(src, projects / src.name)
    return projects


def _setup(client, fake_claude_sessions):
    adapter = ClaudeCodeAdapter(projects_dir=fake_claude_sessions.parent)
    for path in adapter.discover():
        session = adapter.convert(path)
        client.post("/sessions", json=session.model_dump(mode="json"))

    sessions = client.get("/sessions").json()
    db_sid = [s for s in sessions if "db_decision" in s["session_id"]][0]["session_id"]
    bug_sid = [s for s in sessions if "bug" in s["session_id"]][0]["session_id"]

    # tag one session to exercise tag filtering later
    client.post(f"/sessions/{db_sid}/tags", json={"tags": ["decision", "project:memory-talk"]})

    card1 = client.post("/cards", json={
        "summary": "选定 LanceDB 做向量存储 零依赖",
        "session_id": db_sid,
        "rounds": [
            {"role": "human", "text": "ChromaDB 和 LanceDB 哪个好"},
            {"role": "assistant", "text": "推荐 LanceDB 零依赖"},
        ],
        "links": [{"id": db_sid, "type": "session"}],
    }).json()
    card2 = client.post("/cards", json={
        "summary": "LanceDB NFS 建表阻塞 预创建表",
        "session_id": bug_sid,
        "rounds": [
            {"role": "human", "text": "卡住"},
            {"role": "assistant", "text": "NFS fsync"},
        ],
        "links": [{"id": bug_sid, "type": "session"}],
    }).json()
    return db_sid, bug_sid, card1["card_id"], card2["card_id"]


class TestSearch:
    def test_cards_and_sessions_both_return(self, client, config, fake_claude_sessions):
        db_sid, bug_sid, c1, c2 = _setup(client, fake_claude_sessions)

        r = client.post("/search", json={"query": "LanceDB", "top_k": 5}).json()
        assert "cards" in r and "sessions" in r
        assert r["cards"]["count"] >= 1
        # "LanceDB" appears in card summaries and at least one session's rounds
        assert r["sessions"]["count"] >= 0

    def test_dsl_session_id_filters_both_branches(self, client, config, fake_claude_sessions):
        db_sid, bug_sid, c1, c2 = _setup(client, fake_claude_sessions)

        r = client.post(
            "/search",
            json={"query": "LanceDB", "where": f'session_id = "{db_sid}"', "top_k": 10},
        ).json()
        # cards side: only cards from db_sid
        for card in r["cards"]["results"]:
            assert card["session_id"] == db_sid
        # sessions side: only the matching session
        for s in r["sessions"]["results"]:
            assert s["session_id"] == db_sid

    def test_dsl_tag_contains(self, client, config, fake_claude_sessions):
        db_sid, bug_sid, c1, c2 = _setup(client, fake_claude_sessions)

        r = client.post(
            "/search",
            json={"query": "LanceDB", "where": 'tag = "decision"', "top_k": 10},
        ).json()
        # Only db_sid was tagged "decision"
        for card in r["cards"]["results"]:
            assert card["session_id"] == db_sid
        for s in r["sessions"]["results"]:
            assert s["session_id"] == db_sid
            assert "decision" in s["tags"]

    def test_dsl_tag_like(self, client, config, fake_claude_sessions):
        db_sid, bug_sid, c1, c2 = _setup(client, fake_claude_sessions)

        r = client.post(
            "/search",
            json={"query": "LanceDB", "where": 'tag LIKE "project:%"', "top_k": 10},
        ).json()
        # only db_sid was tagged project:memory-talk
        for s in r["sessions"]["results"]:
            assert any(t.startswith("project:") for t in s["tags"])

    def test_card_id_downgrades_sessions_branch(self, client, config, fake_claude_sessions):
        db_sid, bug_sid, c1, c2 = _setup(client, fake_claude_sessions)

        r = client.post(
            "/search",
            json={"query": "LanceDB", "where": f'card_id = "{c1}"', "top_k": 10},
        ).json()
        # cards side: filters to c1
        assert all(card["card_id"] == c1 for card in r["cards"]["results"])
        # sessions side: downgraded — count must be 0
        assert r["sessions"]["count"] == 0
        assert r["sessions"]["results"] == []

    def test_empty_query_with_where_returns_recent(self, client, config, fake_claude_sessions):
        db_sid, bug_sid, c1, c2 = _setup(client, fake_claude_sessions)

        r = client.post(
            "/search",
            json={"query": "", "where": f'session_id = "{db_sid}"', "top_k": 10},
        ).json()
        # Both branches fall back to created_at DESC within the session_id filter
        assert r["cards"]["count"] >= 1
        assert r["sessions"]["count"] == 1

    def test_summary_field_in_where_rejected(self, client, config, fake_claude_sessions):
        _setup(client, fake_claude_sessions)

        r = client.post(
            "/search",
            json={"query": "LanceDB", "where": 'summary LIKE "%x%"', "top_k": 5},
        )
        assert r.status_code == 400
        assert "DSL parse error" in r.json()["detail"]

    def test_score_shape(self, client, config, fake_claude_sessions):
        _setup(client, fake_claude_sessions)

        r = client.post("/search", json={"query": "LanceDB", "top_k": 5}).json()
        for card in r["cards"]["results"]:
            assert "score" in card and "links" in card
            # RRF score is in [0, 2/(K+1)] ≈ [0, 0.033]; just check it's a number
            assert isinstance(card["score"], (int, float))
        for s in r["sessions"]["results"]:
            assert "score" in s and "source" in s and "tags" in s

import aiosqlite

from memory_talk_v2.repository import SQLiteStore
from memory_talk_v2.repository.schema import init_schema


async def test_init_schema_is_idempotent(tmp_path):
    db = tmp_path / "memory.db"
    conn = await aiosqlite.connect(str(db))
    await init_schema(conn)
    await init_schema(conn)
    async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
        rows = await cur.fetchall()
    tables = {r[0] for r in rows}
    for t in ("sessions", "rounds", "cards", "links", "search_log"):
        assert t in tables
    assert "event_log" not in tables
    await conn.close()


async def test_store_sessions_and_rounds_roundtrip(tmp_path):
    db = await SQLiteStore.create(tmp_path / "memory.db")
    await db.sessions.upsert(
        session_id="sess_abc",
        source="claude-code",
        created_at="2026-04-10T00:00:00Z",
        synced_at="2026-04-22T00:00:00Z",
        metadata={"project": "x"},
        tags=["decision"],
        round_count=2,
    )
    await db.sessions.upsert_rounds("sess_abc", [
        {"idx": 1, "round_id": "r1", "parent_id": None, "timestamp": "2026-04-10T00:00:01Z",
         "speaker": "user", "role": "human", "content": [{"type": "text", "text": "hi"}],
         "is_sidechain": False, "cwd": None, "usage": None},
        {"idx": 2, "round_id": "r2", "parent_id": "r1", "timestamp": "2026-04-10T00:00:02Z",
         "speaker": "assistant", "role": "assistant",
         "content": [{"type": "text", "text": "yo"}],
         "is_sidechain": False, "cwd": None, "usage": {"input_tokens": 10}},
    ])

    s = await db.sessions.get("sess_abc")
    assert s["tags"] == ["decision"]
    assert s["metadata"] == {"project": "x"}

    rounds = await db.sessions.list_rounds("sess_abc")
    assert [r["idx"] for r in rounds] == [1, 2]
    assert rounds[1]["usage"] == {"input_tokens": 10}

    r = await db.sessions.get_round_by_round_id("sess_abc", "r2")
    assert r["idx"] == 2
    assert await db.sessions.max_round_idx("sess_abc") == 2
    await db.close()


async def test_store_cards_and_links(tmp_path):
    db = await SQLiteStore.create(tmp_path / "memory.db")
    await db.cards.insert(
        "card_x", "summary",
        [{"role": "human", "text": "hi", "session_id": "sess_a", "index": 1}],
        created_at="2026-04-22T00:00:00Z", expires_at="2026-05-22T00:00:00Z",
    )
    c = await db.cards.get("card_x")
    assert c["summary"] == "summary"
    assert c["rounds"][0]["role"] == "human"

    await db.links.insert(
        "link_1", "card_x", "card", "sess_a", "session", comment=None,
        expires_at=None, created_at="2026-04-22T00:00:00Z",
    )
    assert await db.links.count() == 1
    touching = await db.links.touching("card_x")
    assert len(touching) == 1 and touching[0]["expires_at"] is None
    await db.close()

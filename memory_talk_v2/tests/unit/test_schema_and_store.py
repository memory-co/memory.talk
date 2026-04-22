from memory_talk_v2.storage.sqlite import SQLiteStore
from memory_talk_v2.storage.schema import init_schema
import sqlite3


def test_init_schema_is_idempotent(tmp_path):
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(db)
    init_schema(conn)
    init_schema(conn)  # second run must not raise
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in ("sessions", "rounds", "cards", "links", "ingest_log", "search_log", "event_log"):
        assert t in tables
    conn.close()


def test_store_sessions_and_rounds_roundtrip(tmp_path):
    db = SQLiteStore(tmp_path / "memory.db")
    db.upsert_session(
        session_id="sess_abc",
        source="claude-code",
        created_at="2026-04-10T00:00:00Z",
        synced_at="2026-04-22T00:00:00Z",
        metadata={"project": "x"},
        tags=["decision"],
        round_count=2,
    )
    db.upsert_rounds("sess_abc", [
        {"idx": 1, "round_id": "r1", "parent_id": None, "timestamp": "2026-04-10T00:00:01Z",
         "speaker": "user", "role": "human", "content": [{"type": "text", "text": "hi"}],
         "is_sidechain": False, "cwd": None, "usage": None},
        {"idx": 2, "round_id": "r2", "parent_id": "r1", "timestamp": "2026-04-10T00:00:02Z",
         "speaker": "assistant", "role": "assistant",
         "content": [{"type": "text", "text": "yo"}],
         "is_sidechain": False, "cwd": None, "usage": {"input_tokens": 10}},
    ])

    s = db.get_session("sess_abc")
    assert s["tags"] == ["decision"]
    assert s["metadata"] == {"project": "x"}

    rounds = db.list_rounds("sess_abc")
    assert [r["idx"] for r in rounds] == [1, 2]
    assert rounds[1]["usage"] == {"input_tokens": 10}

    r = db.get_round_by_round_id("sess_abc", "r2")
    assert r["idx"] == 2
    assert db.max_round_idx("sess_abc") == 2


def test_store_cards_and_links(tmp_path):
    db = SQLiteStore(tmp_path / "memory.db")
    db.insert_card("card_x", "summary", [{"role": "human", "text": "hi", "session_id": "sess_a", "index": 1}],
                   created_at="2026-04-22T00:00:00Z", expires_at="2026-05-22T00:00:00Z")
    c = db.get_card("card_x")
    assert c["summary"] == "summary"
    assert c["rounds"][0]["role"] == "human"

    db.insert_link("link_1", "card_x", "card", "sess_a", "session", comment=None,
                   expires_at=None, created_at="2026-04-22T00:00:00Z")
    assert db.count_links() == 1
    touching = db.links_touching("card_x")
    assert len(touching) == 1 and touching[0]["expires_at"] is None


def test_event_log(tmp_path):
    db = SQLiteStore(tmp_path / "memory.db")
    db.insert_event("evt_1", "card_x", "card", "2026-04-22T00:00:00Z",
                    "created", {"summary": "x"})
    events = db.events_for("card_x")
    assert events == [{
        "event_id": "evt_1",
        "object_id": "card_x",
        "object_kind": "card",
        "at": "2026-04-22T00:00:00Z",
        "kind": "created",
        "detail": {"summary": "x"},
    }]


def test_ingest_log(tmp_path):
    db = SQLiteStore(tmp_path / "memory.db")
    assert not db.ingest_seen("sess_a", "sha1")
    db.ingest_record("sess_a", "sha1", "2026-04-22T00:00:00Z")
    assert db.ingest_seen("sess_a", "sha1")
    # idempotent
    db.ingest_record("sess_a", "sha1", "2026-04-22T00:00:00Z")

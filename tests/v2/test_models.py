import pytest
from pydantic import ValidationError
from memory_talk.v2.models import LinkRef, SearchLog, EventLog


def test_link_ref_round_trip():
    lr = LinkRef(
        link_id="link_01jzq7rm",
        target_id="sess_abc123",
        target_type="session",
        comment=None,
        ttl=0,
    )
    d = lr.model_dump()
    assert d["link_id"] == "link_01jzq7rm"
    assert d["target_type"] == "session"


def test_link_ref_rejects_bad_type():
    with pytest.raises(ValidationError):
        LinkRef(
            link_id="link_x", target_id="sess_x", target_type="sidecar",
            comment=None, ttl=0,
        )


def test_search_log_minimal():
    sl = SearchLog(
        search_id="sch_01K",
        query="x",
        where=None,
        top_k=10,
        created_at="2026-04-22T00:00:00Z",
        cards={"count": 0, "results": []},
        sessions={"count": 0, "results": []},
    )
    assert sl.top_k == 10


def test_event_log_minimal():
    ev = EventLog(
        event_id="evt_01K",
        object_id="card_xxx",
        object_kind="card",
        at="2026-04-22T00:00:00Z",
        kind="created",
        detail={"summary": "x", "rounds": [], "default_links": [], "ttl_initial": 2592000},
    )
    assert ev.kind == "created"

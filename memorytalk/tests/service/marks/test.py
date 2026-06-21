"""SessionMarkService.submit_marks — the v4 session-mark write path.

Covers miss→create, hit→link, optimistic lock (409), rounds validation
(first index == 1, strictly ascending, no dups), explicit vs comment issues,
per-card merge across rounds, round coverage (≥90%), DELETE clear, and the
marks/m<n>.yaml canonical.

The seeded session has round_count==5, so ≥90% coverage means ceil(0.9*5)==5
rounds — i.e. all 5. Happy-path tests therefore walk every round (commented
or bare) so the submission passes the coverage gate.
"""
from __future__ import annotations

import pytest

from memorytalk.service.session_marks import (
    MarkConflict, MarkNotFound, MarkServiceError,
    MarkUnavailable, SessionMarkService,
)


async def _submit(svc, session, rounds, last_index=5, description="reading"):
    return await svc.svc.submit_marks(session, last_index, description, rounds)


def _full(n=5, overrides=None):
    overrides = overrides or {}
    out = []
    for i in range(1, n + 1):
        e = {"index": i}
        if i in overrides:
            e.update(overrides[i])
        out.append(e)
    return out


# ────────── happy path: miss creates, hit links ──────────

async def test_miss_creates_card_session_yaml_and_session_marks(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, _full(5, {
        1: {"comment": "context. #why does pty remind the user of tmux？ tail"},
    }))
    # response shape — server auto-assigned m1
    assert res["session_id"] == sid
    assert res["mark"] == "m1"
    r1 = next(rd for rd in res["rounds"] if rd["index"] == 1)
    issue = r1["issues"][0]
    assert issue["is_new"] is True
    assert issue["card_id"].startswith("card_")
    assert issue["indexes"] == "1"     # grounds at the round's own index
    card_id = issue["card_id"]

    assert await marksvc.db.cards.exists(card_id)
    rows = await marksvc.db.session_marks.list_for_session(sid)
    assert [r["mark"] for r in rows] == ["m1"]
    assert rows[0]["last_index"] == 5
    edges = await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1")
    assert len(edges) == 1
    assert edges[0]["card_id"] == card_id
    assert edges[0]["indexes"] == "1"
    # marks/m1.yaml canonical
    doc = await marksvc.svc.read_mark(sid, "m1")
    assert doc["description"] == "reading"
    assert doc["last_index"] == 5
    doc_r1 = next(rd for rd in doc["rounds"] if rd["index"] == 1)
    assert "why does pty remind the user of tmux" in doc_r1["comment"]
    assert doc_r1["issues"][0]["card_id"] == card_id
    assert doc_r1["issues"][0]["is_new"] is True


async def test_hit_links_existing_card(marksvc):
    sid = marksvc.session
    r1 = await _submit(marksvc, sid, _full(5, {
        1: {"comment": "#what is the capital of France？"},
    }))
    card_id = next(rd for rd in r1["rounds"] if rd["index"] == 1)["issues"][0]["card_id"]

    r2 = await _submit(marksvc, sid, _full(5, {
        2: {"comment": "#what is the capital of France？"},
    }))
    iss = next(rd for rd in r2["rounds"] if rd["index"] == 2)["issues"][0]
    assert iss["is_new"] is False
    assert iss["card_id"] == card_id
    edges = await marksvc.db.card_sessions.list_for_card(card_id)
    assert {e["mark"] for e in edges} == {"m1", "m2"}


async def test_mark_without_issue_writes_no_card(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, _full(5, {
        1: {"comment": "just an observation, no question here."},
    }))
    assert all(rd["issues"] == [] for rd in res["rounds"])
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1") == []


async def test_bare_round_covers_no_card(marksvc):
    """Bare rounds (just {index}, no comment) are persisted, contribute
    coverage, and create no card."""
    sid = marksvc.session
    res = await _submit(marksvc, sid, _full(5))   # all bare
    assert all(rd["issues"] == [] for rd in res["rounds"])
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1") == []
    doc = await marksvc.svc.read_mark(sid, "m1")
    assert [rd["index"] for rd in doc["rounds"]] == [1, 2, 3, 4, 5]


# ────────── rounds validation ──────────

async def test_first_index_must_be_1(marksvc):
    with pytest.raises(MarkServiceError) as ei:
        await _submit(marksvc, marksvc.session, [{"index": i} for i in range(2, 6)])
    assert "first round index must be 1" in str(ei.value)
    assert await marksvc.db.session_marks.list_for_session(marksvc.session) == []


async def test_not_strictly_ascending(marksvc):
    with pytest.raises(MarkServiceError) as ei:
        await _submit(marksvc, marksvc.session,
                      [{"index": 1}, {"index": 3}, {"index": 2}, {"index": 4}, {"index": 5}])
    assert "ascending" in str(ei.value)


async def test_duplicate_index(marksvc):
    with pytest.raises(MarkServiceError):
        await _submit(marksvc, marksvc.session,
                      [{"index": 1}, {"index": 2}, {"index": 2}, {"index": 3},
                       {"index": 4}, {"index": 5}])


async def test_index_out_of_range(marksvc):
    with pytest.raises(MarkServiceError):
        await _submit(marksvc, marksvc.session,
                      [{"index": 1}, {"index": 2}, {"index": 3}, {"index": 4}, {"index": 9}])


# ────────── explicit issues + per-card merge ──────────

async def test_explicit_issue_grounds_at_given_indexes(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, _full(5, {
        5: {"issues": [{"issue": "what caused the EMFILE", "indexes": "2-3"}]},
    }))
    r5 = next(rd for rd in res["rounds"] if rd["index"] == 5)
    iss = r5["issues"][0]
    assert iss["indexes"] == "2-3"
    edges = await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1")
    assert edges[0]["card_id"] == iss["card_id"]
    assert edges[0]["indexes"] == "2-3"


async def test_explicit_issue_defaults_to_round_index(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, _full(5, {
        4: {"issues": [{"issue": "some standalone question"}]},   # no indexes
    }))
    r4 = next(rd for rd in res["rounds"] if rd["index"] == 4)
    assert r4["issues"][0]["indexes"] == "4"


async def test_same_card_two_rounds_merges_indexes(marksvc):
    sid = marksvc.session
    q = "#why does pty remind of tmux？"
    res = await _submit(marksvc, sid, _full(5, {2: {"comment": q}, 4: {"comment": q}}))
    card_id = next(rd for rd in res["rounds"] if rd["index"] == 2)["issues"][0]["card_id"]
    edges = await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1")
    # ONE row for the card (PK merge), indexes merged "2,4".
    rows = [e for e in edges if e["card_id"] == card_id]
    assert len(rows) == 1
    assert rows[0]["indexes"] == "2,4"


async def test_multi_issue_round(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, _full(5, {
        3: {"comment": "#first distinct question？ and #second distinct question？"},
    }))
    issues = next(rd for rd in res["rounds"] if rd["index"] == 3)["issues"]
    assert len(issues) == 2
    assert {i["issue"] for i in issues} == {
        "first distinct question", "second distinct question",
    }
    assert issues[0]["card_id"] != issues[1]["card_id"]
    assert all(i["indexes"] == "3" for i in issues)
    edges = await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1")
    assert len(edges) == 2


# ────────── coverage ──────────

async def test_coverage_below_threshold_rejected_nothing_persisted(marksvc):
    sid = marksvc.session
    with pytest.raises(MarkServiceError) as ei:
        await _submit(marksvc, sid, [{"index": 1, "comment": "#a question？"}])
    assert "coverage" in str(ei.value)
    assert "1/5" in str(ei.value)
    assert "90%" in str(ei.value)
    assert await marksvc.db.session_marks.list_for_session(sid) == []
    assert await marksvc.svc.read_mark(sid, "m1") is None


async def test_coverage_just_at_threshold_passes_long_session(data_root):
    """A 52-round session: covering 48/52 (~92%) passes; 12/52 (~23%) is
    rejected with the documented 'coverage 23% (12/52 rounds) < 90%' shape."""
    from memorytalk.config import Config
    from memorytalk.migrations.v3 import init_database as v4_init
    from memorytalk.provider.storage import LocalStorage
    from memorytalk.repository.store import SQLiteStore
    from memorytalk.service.cards import CardService
    from memorytalk.service.events import EventWriter
    from memorytalk.service.searchbase_schema import build_search_backend

    config = Config(data_root)
    config.ensure_dirs()
    conn = await SQLiteStore.open_connection(config.db_path)
    await v4_init.run(conn, data_root=None)
    db = SQLiteStore(conn, config.db_path, LocalStorage(config.data_root))
    await db.sessions.upsert(
        "sess-long0001", "claude-code", "/x",
        "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", {}, 52, "r52",
    )
    search = await build_search_backend(config)
    cards = CardService(db=db, search=search, events=EventWriter(db))
    svc = SessionMarkService(db=db, search=search, cards=cards)
    try:
        # 48/52 ≈ 92% ≥ 90% → OK (need == ceil(0.9*52) == 47).
        res = await svc.submit_marks(
            "sess-long0001", 52, "long read",
            [{"index": i} for i in range(1, 49)],
        )
        assert res["mark"] == "m1"

        # 12/52 ≈ 23% → rejected with the documented message shape.
        with pytest.raises(MarkServiceError) as ei:
            await svc.submit_marks(
                "sess-long0001", 52, "stale",
                [{"index": i} for i in range(1, 13)],
            )
        assert "coverage 23% (12/52 rounds) < 90%" == str(ei.value)
    finally:
        await search.close()
        await conn.close()


# ────────── optimistic lock + auto m<n> ──────────

async def test_optimistic_lock_mismatch_409(marksvc):
    sid = marksvc.session   # round_count == 5
    with pytest.raises(MarkConflict):
        await _submit(marksvc, sid, _full(4), last_index=4)
    assert await marksvc.db.session_marks.list_for_session(sid) == []


async def test_auto_m1_then_m2(marksvc):
    sid = marksvc.session
    r1 = await _submit(marksvc, sid, _full(5))
    assert r1["mark"] == "m1"
    r2 = await _submit(marksvc, sid, _full(5))
    assert r2["mark"] == "m2"
    rows = await marksvc.db.session_marks.list_for_session(sid)
    assert [r["mark"] for r in rows] == ["m1", "m2"]


async def test_empty_rounds_400(marksvc):
    with pytest.raises(MarkServiceError):
        await _submit(marksvc, marksvc.session, [])


async def test_unknown_session_404(marksvc):
    with pytest.raises(MarkNotFound):
        await _submit(marksvc, "sess-doesnotexist", [{"index": 1, "comment": "x"}])


# ────────── degrade when searchbase missing ──────────

async def test_issue_without_searchbase_503(marksvc):
    degraded = SessionMarkService(db=marksvc.db, search=None, cards=marksvc.cards)
    with pytest.raises(MarkUnavailable):
        await degraded.submit_marks(
            marksvc.session, 5, "x",
            _full(5, {1: {"comment": "#needs a card？"}}),
        )
    assert await marksvc.db.session_marks.list_for_session(marksvc.session) == []


async def test_no_issue_without_searchbase_ok(marksvc):
    degraded = SessionMarkService(db=marksvc.db, search=None, cards=marksvc.cards)
    res = await degraded.submit_marks(
        marksvc.session, 5, "x", _full(5, {1: {"comment": "no question"}}),
    )
    assert all(rd["issues"] == [] for rd in res["rounds"])


# ────────── atomicity: embed failure mid-resolve persists nothing ──────────

async def test_embed_failure_midresolve_persists_nothing(marksvc):
    """A runtime embedding failure on the 2nd issue must leave the WHOLE
    submission unpersisted: no session_marks, no card_sessions, no yaml."""
    sid = marksvc.session
    real_nearest = marksvc.search.nearest
    calls = {"n": 0}

    async def flaky_nearest(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("embedding provider down")
        return await real_nearest(*args, **kwargs)

    marksvc.search.nearest = flaky_nearest
    try:
        with pytest.raises(MarkUnavailable):
            await _submit(marksvc, sid, _full(5, {
                1: {"comment": "#first question？"},
                4: {"comment": "#second question？"},
            }))
    finally:
        marksvc.search.nearest = real_nearest

    assert await marksvc.db.session_marks.list_for_session(sid) == []
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1") == []
    assert await marksvc.svc.read_mark(sid, "m1") is None


# ────────── clear_marks ──────────

async def test_clear_marks_removes_marks_and_edges_keeps_card(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, _full(5, {3: {"comment": "#a brand new question？"}}))
    card_id = next(rd for rd in res["rounds"] if rd["index"] == 3)["issues"][0]["card_id"]
    assert await marksvc.db.cards.exists(card_id)

    out = await marksvc.svc.clear_marks(sid)
    assert out == {"session_id": sid, "deleted_marks": 1}

    assert await marksvc.db.session_marks.list_for_session(sid) == []
    assert await marksvc.db.card_sessions.list_for_card(card_id) == []
    assert await marksvc.svc.read_mark(sid, "m1") is None
    # the card itself survives
    assert await marksvc.db.cards.exists(card_id)


async def test_clear_marks_no_marks_is_noop(marksvc):
    out = await marksvc.svc.clear_marks(marksvc.session)
    assert out == {"session_id": marksvc.session, "deleted_marks": 0}


async def test_clear_marks_unknown_session_404(marksvc):
    with pytest.raises(MarkNotFound):
        await marksvc.svc.clear_marks("sess-doesnotexist")


# ────────── integration: interactive walk → real submit ──────────

async def test_interactive_walk_builds_body_that_creates_cards(marksvc, monkeypatch):
    """The client-side step标注 walk accumulates a submission locally; that
    SAME body, fed through the real ``submit_marks``, must create cards +
    card_sessions edges. Proves the interactive path and the file path land
    identically (no special-casing in the service)."""
    from memorytalk.cli import _mark as m

    sid = marksvc.session   # seeded round_count == 5

    rounds = [
        {"index": i, "role": "human" if i % 2 else "assistant",
         "content": [{"type": "text", "text": f"round {i} about pty and tmux"}]}
        for i in range(1, 6)
    ]

    def fake_api(method, path, config, json_body=None, **kw):
        if path == "/v4/read":
            return {"type": "session", "session": {"rounds": rounds}}
        raise AssertionError(f"unexpected api call {method} {path}")

    monkeypatch.setattr(m, "api", fake_api)

    captured = {}

    def post_fn(cfg, session_id, body, json_out):
        captured["body"] = body
        return {"deferred": True}

    def scripted(_answers=iter([
        "",                          # r1 blank
        "#why does pty remind the user of tmux？ wants reconnect",  # r2
        "",                          # r3 blank
        "just EMFILE triage, no question.",                        # r4
        "",                          # r5 blank
    ])):
        return lambda cur: next(_answers, ":q")

    m.run_interactive(
        cfg=None, session_id=sid, json_out=False, post_fn=post_fn,
        ask_description=lambda: "reading the pty/tmux stretch",
        ask_comment=scripted(),
        echo=lambda *_: None,
    )

    body = captured["body"]
    assert body["last_index"] == 5
    assert [rd["index"] for rd in body["rounds"]] == [1, 2, 3, 4, 5]
    # No client-assigned ids — server auto-assigns.
    assert all("id" not in rd for rd in body["rounds"])
    assert "comment" not in body["rounds"][0]                   # r1 blank
    assert "pty" in body["rounds"][1]["comment"]                # r2
    assert "comment" not in body["rounds"][2]                   # r3 blank

    # Feed that exact body through the real submit path.
    result = await marksvc.svc.submit_marks(
        sid, body["last_index"], body["description"], body["rounds"],
    )
    assert result["mark"] == "m1"
    r2 = next(rd for rd in result["rounds"] if rd["index"] == 2)
    issue = r2["issues"][0]
    assert issue["is_new"] is True
    assert await marksvc.db.cards.exists(issue["card_id"])
    edges = await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1")
    assert any(e["card_id"] == issue["card_id"] and e["indexes"] == "2" for e in edges)

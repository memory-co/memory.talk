"""SessionMarkService.submit_marks — the v4 session-mark write path.

Covers miss→create, hit→link, optimistic lock (409), id monotonicity (400),
multi-issue marks, no-issue marks, round coverage (≥90%, id-only entries),
and the marks/m<n>.yaml canonical.

The seeded session has round_count==5, so ≥90% coverage means ceil(0.9*5)==5
rounds — i.e. all 5. Most happy-path tests therefore append an id-only entry
covering whatever rounds the annotated marks don't, so the batch passes the
coverage gate while still exercising the behavior under test.
"""
from __future__ import annotations

import pytest

from memorytalk.service.session_marks import (
    MARK_COVERAGE_THRESHOLD, MarkConflict, MarkNotFound, MarkServiceError,
    MarkUnavailable, SessionMarkService,
)


async def _submit(svc, session, marks, last_index=5, description="reading"):
    return await svc.svc.submit_marks(session, last_index, description, marks)


# ────────── happy path: miss creates, hit links ──────────

async def test_miss_creates_card_session_yaml_and_session_marks(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, [
        {"id": "m1", "indexes": "1-2",
         "mark": "context. #why does pty remind the user of tmux？ tail"},
        {"id": "m2", "indexes": "3-5"},   # id-only → covers the rest (≥90%)
    ])
    # response shape
    assert res["session_id"] == sid
    assert res["last_index"] == 5
    assert len(res["marks"]) == 2
    issue = res["marks"][0]["issues"][0]
    assert issue["is_new"] is True
    assert issue["card_id"].startswith("card_")
    assert issue["indexes"] == "1-2"
    card_id = issue["card_id"]

    # card row exists
    assert await marksvc.db.cards.exists(card_id)
    # session_marks row
    rows = await marksvc.db.session_marks.list_for_session(sid)
    assert [r["mark"] for r in rows] == ["m1", "m2"]
    assert rows[0]["last_index"] == 5
    # card_sessions provenance edge (mark + indexes)
    edges = await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1")
    assert len(edges) == 1
    assert edges[0]["card_id"] == card_id
    assert edges[0]["indexes"] == "1-2"
    # marks/m1.yaml canonical
    doc = await marksvc.svc.read_mark(sid, "m1")
    assert doc["description"] == "reading"
    assert doc["last_index"] == 5
    assert "why does pty remind the user of tmux" in doc["mark"]
    assert doc["issues"][0]["card_id"] == card_id
    assert doc["issues"][0]["is_new"] is True
    assert doc["indexes"] == "1-2"


async def test_hit_links_existing_card(marksvc):
    sid = marksvc.session
    # First submission mints a new card for the issue (id-only m2 pads to 100%).
    r1 = await _submit(marksvc, sid, [
        {"id": "m1", "indexes": "1", "mark": "#what is the capital of France？"},
        {"id": "m2", "indexes": "2-5"},
    ])
    card_id = r1["marks"][0]["issues"][0]["card_id"]
    assert r1["marks"][0]["issues"][0]["is_new"] is True

    # Second submission with the identical issue text → HIT (same card).
    r2 = await _submit(marksvc, sid, [
        {"id": "m3", "indexes": "2", "mark": "#what is the capital of France？"},
        {"id": "m4", "indexes": "1,3-5"},
    ])
    iss = r2["marks"][0]["issues"][0]
    assert iss["is_new"] is False
    assert iss["card_id"] == card_id
    # two provenance edges on the same card (different marks)
    edges = await marksvc.db.card_sessions.list_for_card(card_id)
    assert {e["mark"] for e in edges} == {"m1", "m3"}


async def test_mark_without_issue_writes_no_card(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, [
        {"id": "m1", "indexes": "1-5",
         "mark": "just an observation, no question here."},
    ])
    assert res["marks"][0]["issues"] == []
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1") == []
    doc = await marksvc.svc.read_mark(sid, "m1")
    assert doc["issues"] == []
    # indexes is now always written (it's what coverage counts).
    assert doc["indexes"] == "1-5"


async def test_id_only_entry_covers_no_card(marksvc):
    """An id-only entry ({id, indexes} with no mark text) is accepted,
    persisted, contributes coverage, and creates no card / no issues."""
    sid = marksvc.session
    res = await _submit(marksvc, sid, [
        {"id": "m1", "indexes": "1-5"},   # read whole session, nothing to note
    ])
    assert res["marks"][0]["issues"] == []
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1") == []
    doc = await marksvc.svc.read_mark(sid, "m1")
    assert doc["issues"] == []
    assert doc["mark"] == ""          # empty text persisted
    assert doc["indexes"] == "1-5"


async def test_mixed_annotated_and_id_only_reaches_coverage(marksvc):
    """A mix of an annotated mark (rounds 1-2) + an id-only mark (rounds 3-5)
    reaches ≥90% and passes; the annotated one makes a card, the id-only doesn't."""
    sid = marksvc.session
    res = await _submit(marksvc, sid, [
        {"id": "m1", "indexes": "1-2", "mark": "#a real question？"},
        {"id": "m2", "indexes": "3-5"},
    ])
    assert res["marks"][0]["issues"][0]["is_new"] is True
    assert res["marks"][1]["issues"] == []
    rows = await marksvc.db.session_marks.list_for_session(sid)
    assert [r["mark"] for r in rows] == ["m1", "m2"]


async def test_coverage_below_threshold_rejected_nothing_persisted(marksvc):
    """A submission covering only 1/5 rounds (20% < 90%) is rejected with the
    coverage message; nothing is persisted."""
    sid = marksvc.session
    with pytest.raises(MarkServiceError) as ei:
        await _submit(marksvc, sid, [
            {"id": "m1", "indexes": "1", "mark": "#a question？"},
        ])
    assert "coverage" in str(ei.value)
    assert "1/5" in str(ei.value)
    assert "90%" in str(ei.value)
    assert await marksvc.db.session_marks.list_for_session(sid) == []
    assert await marksvc.svc.read_mark(sid, "m1") is None


async def test_coverage_just_at_threshold_passes_long_session(data_root):
    """A 52-round session: covering 48/52 (~92%) passes; 12/52 (~23%) is
    rejected with the documented 'coverage 23% (12/52 rounds) < 90%' shape."""
    from types import SimpleNamespace as _NS

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
            [{"id": "m1", "indexes": "1-48"}],
        )
        assert len(res["marks"]) == 1

        # 12/52 ≈ 23% → rejected with the documented message shape.
        with pytest.raises(MarkServiceError) as ei:
            await svc.submit_marks(
                "sess-long0001", 52, "stale",
                [{"id": "m2", "indexes": "1-12"}],
            )
        assert "coverage 23% (12/52 rounds) < 90%" == str(ei.value)
    finally:
        await search.close()
        await conn.close()


async def test_indexes_required_400(marksvc):
    """indexes is now required on every mark; missing it → 400."""
    with pytest.raises(MarkServiceError) as ei:
        await _submit(marksvc, marksvc.session, [
            {"id": "m1", "mark": "#a question？"},
        ])
    assert "indexes required" in str(ei.value)


async def test_multi_issue_mark(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, [
        {"id": "m1", "indexes": "3-4",
         "mark": "#first distinct question？ and #second distinct question？"},
        {"id": "m2", "indexes": "1-2,5"},   # id-only pad → ≥90%
    ])
    issues = res["marks"][0]["issues"]
    assert len(issues) == 2
    assert {i["issue"] for i in issues} == {
        "first distinct question", "second distinct question",
    }
    # two distinct new cards, both grounded on 3-4
    assert issues[0]["card_id"] != issues[1]["card_id"]
    assert all(i["indexes"] == "3-4" for i in issues)
    edges = await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1")
    assert len(edges) == 2


# ────────── optimistic lock ──────────

async def test_optimistic_lock_mismatch_409(marksvc):
    sid = marksvc.session   # round_count == 5
    with pytest.raises(MarkConflict):
        await _submit(marksvc, sid, [{"id": "m1", "mark": "x"}], last_index=4)
    # nothing written
    assert await marksvc.db.session_marks.list_for_session(sid) == []


# ────────── id validation ──────────

async def test_missing_id_400(marksvc):
    with pytest.raises(MarkServiceError):
        await _submit(marksvc, marksvc.session, [{"mark": "x"}])


async def test_id_skip_400(marksvc):
    with pytest.raises(MarkServiceError):
        await _submit(marksvc, marksvc.session, [{"id": "m2", "mark": "x"}])


async def test_id_reuse_400(marksvc):
    sid = marksvc.session
    await _submit(marksvc, sid, [{"id": "m1", "indexes": "1-5", "mark": "x"}])
    with pytest.raises(MarkServiceError):
        await _submit(marksvc, sid, [{"id": "m1", "indexes": "1-5", "mark": "y"}])


async def test_continued_marking_resumes_after_max(marksvc):
    sid = marksvc.session
    await _submit(marksvc, sid, [{"id": "m1", "indexes": "1-5", "mark": "a"}])
    # next batch must start at m2 (each batch independently covers ≥90%)
    res = await _submit(marksvc, sid, [
        {"id": "m2", "indexes": "1-3", "mark": "b"},
        {"id": "m3", "indexes": "4-5", "mark": "c"},
    ])
    assert [m["mark"] for m in res["marks"]] == ["m2", "m3"]


async def test_empty_marks_400(marksvc):
    with pytest.raises(MarkServiceError):
        await _submit(marksvc, marksvc.session, [])


async def test_issue_requires_indexes_400(marksvc):
    with pytest.raises(MarkServiceError):
        await _submit(marksvc, marksvc.session, [
            {"id": "m1", "mark": "#an issue with no indexes？"},
        ])


async def test_unknown_session_404(marksvc):
    with pytest.raises(MarkNotFound):
        await _submit(marksvc, "sess-doesnotexist", [{"id": "m1", "mark": "x"}])


# ────────── degrade when searchbase missing ──────────

async def test_issue_without_searchbase_503(marksvc):
    degraded = SessionMarkService(db=marksvc.db, search=None, cards=marksvc.cards)
    with pytest.raises(MarkUnavailable):
        await degraded.submit_marks(
            marksvc.session, 5, "x",
            [{"id": "m1", "indexes": "1-5", "mark": "#needs a card？"}],
        )
    # no partial state
    assert await marksvc.db.session_marks.list_for_session(marksvc.session) == []


async def test_no_issue_without_searchbase_ok(marksvc):
    degraded = SessionMarkService(db=marksvc.db, search=None, cards=marksvc.cards)
    res = await degraded.submit_marks(
        marksvc.session, 5, "x",
        [{"id": "m1", "indexes": "1-5", "mark": "no question"}],
    )
    assert res["marks"][0]["issues"] == []


# ────────── atomicity: embed failure mid-batch persists nothing ──────────

async def test_embed_failure_midbatch_persists_nothing(marksvc):
    """A runtime embedding failure on the 2nd mark's issue must leave the
    WHOLE batch unpersisted: no session_marks, no card_sessions, no yaml,
    no new issue-cards from this batch (整份拒绝 / 不写任何东西)."""
    sid = marksvc.session
    real_nearest = marksvc.search.nearest
    calls = {"n": 0}

    async def flaky_nearest(*args, **kwargs):
        calls["n"] += 1
        # m1's issue resolves; m2's issue blows up (provider falls over).
        if calls["n"] >= 2:
            raise RuntimeError("embedding provider down")
        return await real_nearest(*args, **kwargs)

    marksvc.search.nearest = flaky_nearest
    try:
        with pytest.raises(MarkUnavailable):
            await _submit(marksvc, sid, [
                {"id": "m1", "indexes": "1-3", "mark": "#first question？"},
                {"id": "m2", "indexes": "4-5", "mark": "#second question？"},
            ])
    finally:
        marksvc.search.nearest = real_nearest

    # NOTHING from the batch persisted: no marks, no provenance edges, no yaml.
    assert await marksvc.db.session_marks.list_for_session(sid) == []
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1") == []
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m2") == []
    assert await marksvc.svc.read_mark(sid, "m1") is None
    assert await marksvc.svc.read_mark(sid, "m2") is None


# ────────── integration: interactive walk → real submit ──────────

async def test_interactive_walk_builds_body_that_creates_cards(marksvc, monkeypatch):
    """The client-side step标注 walk accumulates a submission locally; that
    SAME body, fed through the real ``submit_marks``, must create cards +
    card_sessions edges. Proves the interactive path and the file path land
    identically (no special-casing in the service)."""
    from memorytalk.cli import _mark as m

    sid = marksvc.session   # seeded round_count == 5

    # Stub the two read-only HTTP calls the walk makes (read rounds + GET
    # marks for the max seq). The submit goes through the real service.
    rounds = [
        {"index": i, "role": "human" if i % 2 else "assistant",
         "content": [{"type": "text", "text": f"round {i} about pty and tmux"}]}
        for i in range(1, 6)
    ]

    def fake_api(method, path, config, json_body=None, **kw):
        if path == "/v4/read":
            return {"type": "session", "session": {"rounds": rounds}}
        if path.endswith("/marks") and method == "GET":
            return {"marks": []}   # no prior marks → start at m1
        raise AssertionError(f"unexpected api call {method} {path}")

    monkeypatch.setattr(m, "api", fake_api)

    captured = {}

    def post_fn(cfg, session_id, body, json_out):
        # Capture the locally-built body; the real (async) submit runs after
        # the walk so we don't bridge sync→async mid-loop.
        captured["body"] = body
        return {"deferred": True}

    def scripted(_answers=iter([
        "",                          # r1 skip
        "#why does pty remind the user of tmux？ wants reconnect",  # r2 → m1
        "",                          # r3 skip
        "just EMFILE triage, no question.",                        # r4 → m2
        "",                          # r5 skip
    ])):
        return lambda cur: next(_answers, ":q")

    m.run_interactive(
        cfg=None, session_id=sid, json_out=False, post_fn=post_fn,
        ask_description=lambda: "reading the pty/tmux stretch",
        ask_mark=scripted(),
        echo=lambda *_: None,
    )

    # Every round is walked → 5 monotonic marks. Skips (r1/r3/r5) become
    # id-only entries (no ``mark`` key); annotated rounds (r2/r4) carry text.
    # Coverage is therefore 100% (rounds 1-5 all present).
    body = captured["body"]
    assert body["last_index"] == 5
    assert [mk["id"] for mk in body["marks"]] == ["m1", "m2", "m3", "m4", "m5"]
    assert [mk["indexes"] for mk in body["marks"]] == ["1", "2", "3", "4", "5"]
    # id-only skips carry no mark text; annotated rounds do.
    assert "mark" not in body["marks"][0]                       # r1 skip
    assert "pty" in body["marks"][1]["mark"]                    # r2 annotated
    assert "mark" not in body["marks"][2]                       # r3 skip
    assert "EMFILE" in body["marks"][3]["mark"]                 # r4 annotated
    assert "mark" not in body["marks"][4]                       # r5 skip

    # Feed that exact body through the real submit path.
    result = await marksvc.svc.submit_marks(
        sid, body["last_index"], body["description"], body["marks"],
    )

    # The real submit created a card for m2's #…？ and an edge.
    m2 = next(mk for mk in result["marks"] if mk["mark"] == "m2")
    issue = m2["issues"][0]
    assert issue["is_new"] is True
    assert issue["card_id"].startswith("card_")
    assert await marksvc.db.cards.exists(issue["card_id"])
    edges = await marksvc.db.card_sessions.list_cards_for_mark(sid, "m2")
    assert edges[0]["card_id"] == issue["card_id"]
    assert edges[0]["indexes"] == "2"
    # m1 (id-only skip) and m4 (no #…？) → no card, no edge.
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1") == []
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m4") == []

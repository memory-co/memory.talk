"""SessionMarkService.submit_marks — the v4 session-mark write path.

Covers miss→create, hit→link, optimistic lock (409), id monotonicity (400),
multi-issue marks, no-issue marks, and the marks/m<n>.yaml canonical.
"""
from __future__ import annotations

import pytest

from memorytalk.service.session_marks import (
    MarkConflict, MarkNotFound, MarkServiceError, MarkUnavailable,
    SessionMarkService,
)


async def _submit(svc, session, marks, last_index=5, description="reading"):
    return await svc.svc.submit_marks(session, last_index, description, marks)


# ────────── happy path: miss creates, hit links ──────────

async def test_miss_creates_card_session_yaml_and_session_marks(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, [
        {"id": "m1", "indexes": "1-2",
         "mark": "context. #why does pty remind the user of tmux？ tail"},
    ])
    # response shape
    assert res["session_id"] == sid
    assert res["last_index"] == 5
    assert len(res["marks"]) == 1
    issue = res["marks"][0]["issues"][0]
    assert issue["is_new"] is True
    assert issue["card_id"].startswith("card_")
    assert issue["indexes"] == "1-2"
    card_id = issue["card_id"]

    # card row exists
    assert await marksvc.db.cards.exists(card_id)
    # session_marks row
    rows = await marksvc.db.session_marks.list_for_session(sid)
    assert [r["mark"] for r in rows] == ["m1"]
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
    # First submission mints a new card for the issue.
    r1 = await _submit(marksvc, sid, [
        {"id": "m1", "indexes": "1", "mark": "#what is the capital of France？"},
    ])
    card_id = r1["marks"][0]["issues"][0]["card_id"]
    assert r1["marks"][0]["issues"][0]["is_new"] is True

    # Second submission with the identical issue text → HIT (same card).
    r2 = await _submit(marksvc, sid, [
        {"id": "m2", "indexes": "2", "mark": "#what is the capital of France？"},
    ])
    iss = r2["marks"][0]["issues"][0]
    assert iss["is_new"] is False
    assert iss["card_id"] == card_id
    # two provenance edges on the same card (different marks)
    edges = await marksvc.db.card_sessions.list_for_card(card_id)
    assert {e["mark"] for e in edges} == {"m1", "m2"}


async def test_mark_without_issue_writes_no_card(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, [
        {"id": "m1", "mark": "just an observation, no question here."},
    ])
    assert res["marks"][0]["issues"] == []
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1") == []
    doc = await marksvc.svc.read_mark(sid, "m1")
    assert doc["issues"] == []
    assert "indexes" not in doc   # omitted when no #…？


async def test_multi_issue_mark(marksvc):
    sid = marksvc.session
    res = await _submit(marksvc, sid, [
        {"id": "m1", "indexes": "3-4",
         "mark": "#first distinct question？ and #second distinct question？"},
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
    await _submit(marksvc, sid, [{"id": "m1", "mark": "x"}])
    with pytest.raises(MarkServiceError):
        await _submit(marksvc, sid, [{"id": "m1", "mark": "y"}])


async def test_continued_marking_resumes_after_max(marksvc):
    sid = marksvc.session
    await _submit(marksvc, sid, [{"id": "m1", "mark": "a"}])
    # next batch must start at m2
    res = await _submit(marksvc, sid, [
        {"id": "m2", "mark": "b"}, {"id": "m3", "mark": "c"},
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
            [{"id": "m1", "indexes": "1", "mark": "#needs a card？"}],
        )
    # no partial state
    assert await marksvc.db.session_marks.list_for_session(marksvc.session) == []


async def test_no_issue_without_searchbase_ok(marksvc):
    degraded = SessionMarkService(db=marksvc.db, search=None, cards=marksvc.cards)
    res = await degraded.submit_marks(
        marksvc.session, 5, "x", [{"id": "m1", "mark": "no question"}],
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
                {"id": "m1", "indexes": "1", "mark": "#first question？"},
                {"id": "m2", "indexes": "2", "mark": "#second question？"},
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

    # The locally-built body: monotonic ids, single-index auto indexes.
    body = captured["body"]
    assert body["last_index"] == 5
    assert [mk["id"] for mk in body["marks"]] == ["m1", "m2"]
    assert body["marks"][0]["indexes"] == "2"   # current round, not a range
    assert body["marks"][1]["indexes"] == "4"

    # Feed that exact body through the real submit path.
    result = await marksvc.svc.submit_marks(
        sid, body["last_index"], body["description"], body["marks"],
    )

    # The real submit created a card for m1's #…？ and an edge.
    m1 = next(mk for mk in result["marks"] if mk["mark"] == "m1")
    issue = m1["issues"][0]
    assert issue["is_new"] is True
    assert issue["card_id"].startswith("card_")
    assert await marksvc.db.cards.exists(issue["card_id"])
    edges = await marksvc.db.card_sessions.list_cards_for_mark(sid, "m1")
    assert edges[0]["card_id"] == issue["card_id"]
    assert edges[0]["indexes"] == "2"
    # m2 had no #…？ → no card, no edge.
    m2 = next(mk for mk in result["marks"] if mk["mark"] == "m2")
    assert m2["issues"] == []
    assert await marksvc.db.card_sessions.list_cards_for_mark(sid, "m2") == []

"""session mark CLI — file mode body mapping, rendering, interactive smoke.

The /v4 endpoint behaviour is covered by tests/api/test_session_marks.py;
here we pin the CLI surface (what body file/pipe mode POSTs, the rendered
result, the interactive walk from round 1, and clear-marks) by stubbing the
HTTP layer.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

import memorytalk.cli.session as session_mod
import memorytalk.cli._mark as mark_mod


@pytest.fixture
def captured(monkeypatch):
    calls = []
    responses = {}

    def fake_api(method, path, config, json_body=None, **kw):
        calls.append((method, path, json_body))
        for suffix, resp in responses.items():
            if path.endswith(suffix):
                return resp
        return {"status": "ok"}

    # Both modules reference ``api`` by name; stub both bindings.
    monkeypatch.setattr(session_mod, "api", fake_api)
    monkeypatch.setattr(mark_mod, "api", fake_api)
    return type("C", (), {"calls": calls, "responses": responses})()


def _invoke(args, input=None):
    return CliRunner().invoke(session_mod.session, args, input=input)


def _submit_resp(sid="sess-x"):
    return {
        "session_id": sid, "mark": "m1",
        "rounds": [
            {"index": 1, "issues": []},
            {"index": 2, "comment": "#why pty reminds of tmux？", "issues": [
                {"issue": "why pty reminds of tmux", "card_id": "card_01",
                 "is_new": True, "indexes": "2"}]},
        ],
    }


# ────────── help / structure ──────────

def test_mark_help_lists_options():
    r = _invoke(["mark", "--help"])
    assert r.exit_code == 0
    assert "--session" in r.output
    assert "--mark" in r.output


# ────────── file mode ──────────

def test_file_mode_posts_submission(captured, tmp_path):
    captured.responses["/marks"] = _submit_resp("sess-abc")
    yaml_path = tmp_path / "sub.yaml"
    yaml_path.write_text(
        "last_index: 5\n"
        "description: reading the pty stretch\n"
        "rounds:\n"
        "  - index: 1\n"
        "  - index: 2\n"
        "    comment: |\n"
        "      user pivoted. #why pty reminds of tmux？\n"
        "  - index: 3\n"
        "  - index: 4\n"
        "  - index: 5\n",
        encoding="utf-8",
    )
    r = _invoke(["mark", "--session", "sess-abc", "--mark", str(yaml_path)])
    assert r.exit_code == 0, r.output
    method, path, body = captured.calls[0]
    assert method == "POST"
    assert path == "/v4/sessions/sess-abc/marks"
    assert body["last_index"] == 5
    assert body["description"] == "reading the pty stretch"
    assert [rd["index"] for rd in body["rounds"]] == [1, 2, 3, 4, 5]
    assert "#why pty reminds of tmux" in body["rounds"][1]["comment"]
    # round 1 has no comment key
    assert "comment" not in body["rounds"][0]
    # rendered result shows the new card
    assert "new card" in r.output
    assert "card_01" in r.output


def test_file_mode_stdin(captured):
    captured.responses["/marks"] = _submit_resp()
    submission = (
        "last_index: 2\n"
        "description: scene\n"
        "rounds:\n"
        "  - index: 1\n"
        "    comment: an observation\n"
        "  - index: 2\n"
    )
    r = _invoke(["mark", "--session", "sess-x", "--mark", "-"], input=submission)
    assert r.exit_code == 0, r.output
    assert captured.calls[0][1] == "/v4/sessions/sess-x/marks"


def test_file_mode_invalid_yaml_exits_1(captured, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("last_index: 5\nrounds: [unterminated\n", encoding="utf-8")
    r = _invoke(["mark", "--session", "sess-x", "--mark", str(bad)])
    assert r.exit_code == 1
    assert captured.calls == []   # never POSTed


def test_file_mode_missing_rounds_exits_1(captured, tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text("last_index: 5\ndescription: x\n", encoding="utf-8")
    r = _invoke(["mark", "--session", "sess-x", "--mark", str(p)])
    assert r.exit_code == 1
    assert captured.calls == []


def test_file_mode_json_output(captured, tmp_path):
    captured.responses["/marks"] = _submit_resp()
    p = tmp_path / "p.yaml"
    p.write_text(
        "last_index: 1\ndescription: x\nrounds:\n  - index: 1\n    comment: obs\n",
        encoding="utf-8",
    )
    r = _invoke(["mark", "--session", "sess-x", "--mark", str(p), "--json"])
    assert r.exit_code == 0, r.output
    assert '"session_id"' in r.output


# ────────── clear-marks ──────────

def test_clear_marks_calls_delete(captured):
    captured.responses["/marks"] = {"session_id": "sess-x", "deleted_marks": 3}
    r = _invoke(["clear-marks", "sess-x"])
    assert r.exit_code == 0, r.output
    method, path, _ = captured.calls[0]
    assert method == "DELETE"
    assert path == "/v4/sessions/sess-x/marks"
    assert "cleared 3 mark(s) for sess-x" in r.output


def test_clear_marks_json(captured):
    captured.responses["/marks"] = {"session_id": "sess-x", "deleted_marks": 0}
    r = _invoke(["clear-marks", "sess-x", "--json"])
    assert r.exit_code == 0, r.output
    assert '"deleted_marks"' in r.output


# ────────── interactive mode: client-side step标注 ──────────
#
# The walk is driven through an injectable input seam (``ask_description`` /
# ``ask_comment``) so tests can script the loop deterministically — no real
# terminal / questionary. We call ``run_interactive`` directly and assert on
# the locally-built submission body that flows into ``post_fn``.

from memorytalk.cli._http import ApiError


def _read_resp(sid="sess-i", n=3):
    return {
        "type": "session",
        "session": {
            "session_id": sid,
            "rounds": [
                {"index": i, "role": "human" if i % 2 else "assistant",
                 "content": [{"type": "text", "text": f"round {i} text"}]}
                for i in range(1, n + 1)
            ],
        },
    }


def _scripted(*answers):
    """Build an ``ask_comment`` that returns the given answers in sequence,
    then ``:q`` once exhausted (so a runaway loop can't hang the test)."""
    it = iter(answers)

    def ask(cur):
        try:
            return next(it)
        except StopIteration:
            return ":q"
    return ask


@pytest.fixture
def walker(monkeypatch):
    """Drive ``run_interactive`` directly: stub the HTTP layer and capture
    whatever body ``post_fn`` receives. Returns a small harness."""
    from memorytalk.cli import _mark as m

    state = {"read": None, "posted": None,
             "submit_resp": {"session_id": "sess-i", "mark": "m1", "rounds": []}}

    def fake_api(method, path, config, json_body=None, **kw):
        if path == "/v4/read":
            return state["read"]
        return {"status": "ok"}

    monkeypatch.setattr(m, "api", fake_api)

    def post_fn(cfg, sid, body, json_out):
        state["posted"] = body
        return state["submit_resp"]

    echoes = []

    def run(ask_description=lambda: "scene", ask_comment=None, **kw):
        return m.run_interactive(
            cfg=None, session_id="sess-i", json_out=False, post_fn=post_fn,
            ask_description=ask_description, ask_comment=ask_comment or _scripted(),
            echo=echoes.append, **kw,
        )

    return type("W", (), {
        "state": state, "run": staticmethod(run), "echoes": echoes,
        "mark_mod": m, "post_fn": post_fn,
    })()


def test_interactive_walks_from_round_1(walker):
    walker.state["read"] = _read_resp("sess-i", n=3)
    result = walker.run(
        ask_description=lambda: "my scenario",
        ask_comment=_scripted("", "#first question？", "#second question？"),
    )
    body = walker.state["posted"]
    assert body is not None
    assert body["last_index"] == 3
    assert body["description"] == "my scenario"
    # Walked rounds 1..3 from index 1 (100% coverage).
    assert [rd["index"] for rd in body["rounds"]] == [1, 2, 3]
    # r1 blank → no comment key; r2/r3 carry comments.
    assert "comment" not in body["rounds"][0]
    assert body["rounds"][1]["comment"] == "#first question？"
    assert body["rounds"][2]["comment"] == "#second question？"
    # NO client-assigned m<n> ids in the body — server auto-assigns.
    assert all("id" not in rd for rd in body["rounds"])
    assert result == walker.state["submit_resp"]


def test_interactive_quit_marks_nothing(walker):
    walker.state["read"] = _read_resp("sess-i", n=3)
    result = walker.run(ask_comment=_scripted(":q"))
    assert result is None
    assert walker.state["posted"] is None   # never POSTed
    assert any("nothing marked" in e for e in walker.echoes)


def test_interactive_early_quit_below_coverage_blocked(walker):
    walker.state["read"] = _read_resp("sess-i", n=5)
    # Comment r1, then :q — only 1/5 covered (20% < 90%) → blocked, not POSTed.
    result = walker.run(ask_comment=_scripted("only r1", ":q"))
    assert result is None
    assert walker.state["posted"] is None
    assert any("coverage" in e and "90%" in e for e in walker.echoes)


def test_interactive_full_walk_with_blanks_reaches_coverage(walker):
    walker.state["read"] = _read_resp("sess-i", n=5)
    # Step every round: comment some, blank others → 100% coverage → POSTs.
    walker.run(ask_comment=_scripted("", "#q？", "", "", "note"))
    body = walker.state["posted"]
    assert body is not None
    assert [rd["index"] for rd in body["rounds"]] == [1, 2, 3, 4, 5]
    # 3 blank (no comment) + 2 commented.
    assert sum("comment" not in rd for rd in body["rounds"]) == 3


def test_interactive_back_rewalks_without_duplicating(walker):
    walker.state["read"] = _read_resp("sess-i", n=3)
    # r1: comment → r2: :back (re-show r1) → r1: blank (overwrites) → r2 → r3.
    walker.run(ask_comment=_scripted("comment r1", ":back", "", "blank r2", "comment r3"))
    body = walker.state["posted"]
    # Each index recorded once (no dup), in ascending order.
    assert [rd["index"] for rd in body["rounds"]] == [1, 2, 3]
    # r1 was overwritten by the blank on re-walk.
    assert "comment" not in body["rounds"][0]
    assert body["rounds"][1]["comment"] == "blank r2"
    assert body["rounds"][2]["comment"] == "comment r3"


def test_interactive_empty_session(walker):
    walker.state["read"] = {"type": "session", "session": {"rounds": []}}
    result = walker.run(ask_comment=_scripted("x"))
    assert result is None
    assert walker.state["posted"] is None
    assert any("no rounds" in e for e in walker.echoes)


def test_interactive_single_round(walker):
    walker.state["read"] = _read_resp("sess-i", n=1)
    walker.run(ask_comment=_scripted("only round comment"))
    body = walker.state["posted"]
    assert [rd["index"] for rd in body["rounds"]] == [1]
    assert body["rounds"][0]["comment"] == "only round comment"


def test_render_window_single_round_no_prev(walker):
    out = walker.mark_mod.render_window(None, {"index": 1, "role": "human",
                                               "content": [{"type": "text", "text": "hi"}]})
    assert "round 1" in out
    assert "标这里" in out
    assert "context" not in out   # no prev panel


def test_render_window_truncates_long_text(walker):
    long = "x" * 5000
    out = walker.mark_mod.render_window(
        None, {"index": 1, "role": "human", "content": [{"type": "text", "text": long}]})
    assert "…" in out
    assert len(out) < 5000


def test_interactive_409_clean_message(walker, monkeypatch):
    walker.state["read"] = _read_resp("sess-i", n=3)

    def boom_post(cfg, sid, body, json_out):
        from memorytalk.cli.session import _post_marks
        return _post_marks(cfg, sid, body, json_out)

    def fake_api(method, path, config, json_body=None, **kw):
        raise ApiError(409, {"detail": "session advanced (last_index 3 ≠ current 5)"})

    monkeypatch.setattr(session_mod, "api", fake_api)
    errs = []
    monkeypatch.setattr(session_mod, "_emit_err",
                        lambda json_out, msg: errs.append(msg))

    with pytest.raises(SystemExit):
        walker.mark_mod.run_interactive(
            cfg=None, session_id="sess-i", json_out=False, post_fn=boom_post,
            ask_description=lambda: "scene",
            # Walk all 3 rounds → 100% coverage → it POSTs.
            ask_comment=_scripted("a comment", "", ""),
            echo=walker.echoes.append,
        )
    assert any("session advanced" in e for e in errs)

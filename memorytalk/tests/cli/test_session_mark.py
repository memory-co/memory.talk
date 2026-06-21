"""session mark CLI — file mode body mapping, rendering, interactive smoke.

The /v4 endpoint behaviour is covered by tests/api/test_session_marks.py;
here we pin the CLI surface (what body file/pipe mode POSTs, the rendered
result, and the interactive loop's collection) by stubbing the HTTP layer.
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
        "session_id": sid, "last_index": 5,
        "marks": [
            {"mark": "m1", "issues": [
                {"issue": "why pty reminds of tmux", "card_id": "card_01",
                 "is_new": True, "indexes": "3-4"}]},
            {"mark": "m2", "issues": []},
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
        "marks:\n"
        "  - id: m1\n"
        "    indexes: 3-4\n"
        "    mark: |\n"
        "      user pivoted. #why pty reminds of tmux？\n"
        "  - id: m2\n"
        "    mark: just EMFILE triage\n",
        encoding="utf-8",
    )
    r = _invoke(["mark", "--session", "sess-abc", "--mark", str(yaml_path)])
    assert r.exit_code == 0, r.output
    method, path, body = captured.calls[0]
    assert method == "POST"
    assert path == "/v4/sessions/sess-abc/marks"
    assert body["last_index"] == 5
    assert body["description"] == "reading the pty stretch"
    assert [m["id"] for m in body["marks"]] == ["m1", "m2"]
    assert body["marks"][0]["indexes"] == "3-4"
    assert "#why pty reminds of tmux" in body["marks"][0]["mark"]
    # m2 has no indexes key
    assert "indexes" not in body["marks"][1]
    # rendered result shows the new card
    assert "new card" in r.output
    assert "card_01" in r.output


def test_file_mode_stdin(captured):
    captured.responses["/marks"] = _submit_resp()
    submission = (
        "last_index: 5\n"
        "description: scene\n"
        "marks:\n"
        "  - id: m1\n"
        "    mark: an observation\n"
    )
    r = _invoke(["mark", "--session", "sess-x", "--mark", "-"], input=submission)
    assert r.exit_code == 0, r.output
    assert captured.calls[0][1] == "/v4/sessions/sess-x/marks"


def test_file_mode_invalid_yaml_exits_1(captured, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("last_index: 5\nmarks: [unterminated\n", encoding="utf-8")
    r = _invoke(["mark", "--session", "sess-x", "--mark", str(bad)])
    assert r.exit_code == 1
    assert captured.calls == []   # never POSTed


def test_file_mode_missing_marks_exits_1(captured, tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text("last_index: 5\ndescription: x\n", encoding="utf-8")
    r = _invoke(["mark", "--session", "sess-x", "--mark", str(p)])
    assert r.exit_code == 1
    assert captured.calls == []


def test_file_mode_json_output(captured, tmp_path):
    captured.responses["/marks"] = _submit_resp()
    p = tmp_path / "p.yaml"
    p.write_text(
        "last_index: 5\ndescription: x\nmarks:\n  - id: m1\n    mark: obs\n",
        encoding="utf-8",
    )
    r = _invoke(["mark", "--session", "sess-x", "--mark", str(p), "--json"])
    assert r.exit_code == 0, r.output
    assert '"session_id"' in r.output


# ────────── interactive mode: client-side step标注 ──────────
#
# The walk is driven through an injectable input seam (``ask_description`` /
# ``ask_mark``) so tests can script the loop deterministically — no real
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


def _scripted_marks(*answers):
    """Build an ``ask_mark`` that returns the given answers in sequence,
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

    state = {"read": None, "marks_list": {"marks": []}, "posted": None,
             "submit_resp": {"session_id": "sess-i", "last_index": 3, "marks": []}}

    def fake_api(method, path, config, json_body=None, **kw):
        if path == "/v4/read":
            return state["read"]
        if path.endswith("/marks") and method == "GET":
            return state["marks_list"]
        return {"status": "ok"}

    monkeypatch.setattr(m, "api", fake_api)

    def post_fn(cfg, sid, body, json_out):
        state["posted"] = body
        return state["submit_resp"]

    echoes = []

    def run(ask_description=lambda: "scene", ask_mark=None, **kw):
        return m.run_interactive(
            cfg=None, session_id="sess-i", json_out=False, post_fn=post_fn,
            ask_description=ask_description, ask_mark=ask_mark or _scripted_marks(),
            echo=echoes.append, **kw,
        )

    return type("W", (), {
        "state": state, "run": staticmethod(run), "echoes": echoes,
        "mark_mod": m, "post_fn": post_fn,
    })()


def test_interactive_collects_and_posts(walker):
    walker.state["read"] = _read_resp("sess-i", n=3)
    # Walk r1,r2,r3. Skip r1 (blank → id-only coverage entry), mark r2 & r3.
    result = walker.run(
        ask_description=lambda: "my scenario",
        ask_mark=_scripted_marks("", "#first question？", "#second question？"),
    )
    body = walker.state["posted"]
    assert body is not None
    assert body["last_index"] == 3
    assert body["description"] == "my scenario"
    # Every round walked → monotonic ids covering all 3 rounds (100%).
    assert [mk["id"] for mk in body["marks"]] == ["m1", "m2", "m3"]
    assert [mk["indexes"] for mk in body["marks"]] == ["1", "2", "3"]
    # r1 was a skip → id-only entry (no mark text); r2/r3 carry text.
    assert "mark" not in body["marks"][0]
    assert body["marks"][1]["mark"] == "#first question？"
    assert body["marks"][2]["mark"] == "#second question？"
    assert result == walker.state["submit_resp"]


def test_interactive_monotonic_continues_from_existing(walker):
    walker.state["read"] = _read_resp("sess-i", n=3)
    # Session already has m1,m2 → new marks continue at m3,m4.
    walker.state["marks_list"] = {"marks": [{"mark": "m1"}, {"mark": "m2"}]}
    walker.run(ask_mark=_scripted_marks("first", "second", "third"))
    body = walker.state["posted"]
    assert [mk["id"] for mk in body["marks"]] == ["m3", "m4", "m5"]


def test_interactive_quit_marks_nothing(walker):
    walker.state["read"] = _read_resp("sess-i", n=3)
    result = walker.run(ask_mark=_scripted_marks(":q"))
    assert result is None
    assert walker.state["posted"] is None   # never POSTed
    assert any("nothing marked" in e for e in walker.echoes)


def test_interactive_early_quit_below_coverage_blocked(walker):
    walker.state["read"] = _read_resp("sess-i", n=5)
    # Mark r1, then :q — only 1/5 covered (20% < 90%) → blocked, not POSTed.
    result = walker.run(ask_mark=_scripted_marks("only r1", ":q"))
    assert result is None
    assert walker.state["posted"] is None
    assert any("coverage" in e and "90%" in e for e in walker.echoes)


def test_interactive_full_walk_with_skips_reaches_coverage(walker):
    walker.state["read"] = _read_resp("sess-i", n=5)
    # Step every round: mark some, skip others → 100% coverage → POSTs.
    walker.run(ask_mark=_scripted_marks("", "#q？", "", "", "note"))
    body = walker.state["posted"]
    assert body is not None
    assert [mk["indexes"] for mk in body["marks"]] == ["1", "2", "3", "4", "5"]
    # 3 id-only skips + 2 annotated.
    assert sum("mark" not in mk for mk in body["marks"]) == 3


def test_interactive_skip_then_mark(walker):
    walker.state["read"] = _read_resp("sess-i", n=3)
    # blank "skips" r1 & r2 → id-only coverage entries, then mark r3.
    walker.run(ask_mark=_scripted_marks("", "", "#a question？"))
    body = walker.state["posted"]
    assert [mk["id"] for mk in body["marks"]] == ["m1", "m2", "m3"]
    assert [mk["indexes"] for mk in body["marks"]] == ["1", "2", "3"]
    # r1/r2 id-only (no text), r3 carries the question.
    assert "mark" not in body["marks"][0]
    assert "mark" not in body["marks"][1]
    assert body["marks"][2]["mark"] == "#a question？"


def test_interactive_back_rewalks_without_unassigning(walker):
    walker.state["read"] = _read_resp("sess-i", n=3)
    # r1: mark (m1) → r2: :back (re-show r1) → r1: skip → r2: skip → r3: mark.
    # :back must NOT drop the already-assigned m1; later steps append-only.
    # Each blank skip now mints an id-only coverage entry, so we collect m1..m4.
    walker.run(ask_mark=_scripted_marks("mark r1", ":back", "", "", "mark r3"))
    body = walker.state["posted"]
    assert [mk["id"] for mk in body["marks"]] == ["m1", "m2", "m3", "m4"]
    assert [mk["indexes"] for mk in body["marks"]] == ["1", "1", "2", "3"]
    assert body["marks"][0]["mark"] == "mark r1"
    assert "mark" not in body["marks"][1]   # id-only skip of r1
    assert "mark" not in body["marks"][2]   # id-only skip of r2
    assert body["marks"][3]["mark"] == "mark r3"


def test_interactive_empty_session(walker):
    walker.state["read"] = {"type": "session", "session": {"rounds": []}}
    result = walker.run(ask_mark=_scripted_marks("x"))
    assert result is None
    assert walker.state["posted"] is None
    assert any("no rounds" in e for e in walker.echoes)


def test_interactive_single_round(walker):
    walker.state["read"] = _read_resp("sess-i", n=1)
    walker.run(ask_mark=_scripted_marks("only round mark"))
    body = walker.state["posted"]
    assert [mk["id"] for mk in body["marks"]] == ["m1"]
    assert body["marks"][0]["indexes"] == "1"


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
        # Mirror session._post_marks' 409 surfacing.
        from memorytalk.cli.session import _post_marks
        return _post_marks(cfg, sid, body, json_out)

    # Make the real POST raise 409 via the stubbed api in session module.
    def fake_api(method, path, config, json_body=None, **kw):
        raise ApiError(409, {"detail": "session advanced (last_index 3 ≠ current 5)"})

    monkeypatch.setattr(session_mod, "api", fake_api)
    # Capture stderr-bound _emit_err output.
    errs = []
    monkeypatch.setattr(session_mod, "_emit_err",
                        lambda json_out, msg: errs.append(msg))

    with pytest.raises(SystemExit):
        walker.mark_mod.run_interactive(
            cfg=None, session_id="sess-i", json_out=False, post_fn=boom_post,
            ask_description=lambda: "scene",
            # Walk all 3 rounds (mark + 2 skips) → 100% coverage → it POSTs.
            ask_mark=_scripted_marks("a mark", "", ""),
            echo=walker.echoes.append,
        )
    assert any("session advanced" in e for e in errs)

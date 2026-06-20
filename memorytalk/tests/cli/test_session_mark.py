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


# ────────── interactive mode (line-based) ──────────

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


def test_interactive_collects_and_posts(captured):
    captured.responses["/read"] = _read_resp("sess-i", n=3)
    captured.responses["/marks"] = _submit_resp("sess-i")
    # description prompt, then per-window mark> prompts. Windows:
    # [r1,r2] mark r2, [r2,r3] mark r3. Two marks typed.
    stdin = "\n".join([
        "my scenario",                       # description
        "#first question？ for r2",          # mark r2 → m1
        "#second question？ for r3",          # mark r3 → m2
    ]) + "\n"
    r = _invoke(["mark", "--session", "sess-i"], input=stdin)
    assert r.exit_code == 0, r.output
    # last call is the submit POST
    post = [c for c in captured.calls if c[0] == "POST"][-1]
    method, path, body = post
    assert path == "/v4/sessions/sess-i/marks"
    assert body["last_index"] == 3
    assert body["description"] == "my scenario"
    assert [m["id"] for m in body["marks"]] == ["m1", "m2"]
    assert body["marks"][0]["indexes"] == "1-2"
    assert body["marks"][1]["indexes"] == "2-3"


def test_interactive_quit_marks_nothing(captured):
    captured.responses["/read"] = _read_resp("sess-i", n=3)
    stdin = "scene\n:q\n"
    r = _invoke(["mark", "--session", "sess-i"], input=stdin)
    assert r.exit_code == 0
    assert "(nothing marked)" in r.output
    # no submit POST happened
    assert all(c[1] != "/v4/sessions/sess-i/marks" for c in captured.calls)


def test_interactive_skip_then_mark(captured):
    captured.responses["/read"] = _read_resp("sess-i", n=3)
    captured.responses["/marks"] = _submit_resp("sess-i")
    # blank skips r2, then mark r3.
    stdin = "scene\n\n#a question？\n"
    r = _invoke(["mark", "--session", "sess-i"], input=stdin)
    assert r.exit_code == 0, r.output
    post = [c for c in captured.calls if c[0] == "POST"][-1]
    body = post[2]
    assert [m["id"] for m in body["marks"]] == ["m1"]
    assert body["marks"][0]["indexes"] == "2-3"   # window [r2,r3]

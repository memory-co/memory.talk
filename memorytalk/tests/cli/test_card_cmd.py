"""card CLI — flag→request mapping, parsing helpers, formatters.

The /v4 endpoint behaviour is covered by tests/api/v4; here we verify the
client surface (what body each command sends, arg parsing, markdown out)
by stubbing ``cli.card.api``.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

import memorytalk.cli.card as card_mod
from memorytalk.cli.card import _parse_source, _read_text_arg


@pytest.fixture
def captured(monkeypatch):
    """Stub the HTTP layer; record (method, path, body) and return a canned
    response keyed by path."""
    calls = []
    responses = {}

    def fake_api(method, path, config, json_body=None, **kw):
        calls.append((method, path, json_body))
        for suffix, resp in responses.items():
            if path.endswith(suffix):
                return resp
        return {"status": "ok"}

    monkeypatch.setattr(card_mod, "api", fake_api)
    return type("C", (), {"calls": calls, "responses": responses})()


def _invoke(args, input=None):
    return CliRunner().invoke(card_mod.card, args, input=input)


# ────────── help / structure ──────────

def test_card_group_help():
    r = _invoke(["--help"])
    assert r.exit_code == 0
    for sub in ("create", "position", "review", "link"):
        assert sub in r.output


@pytest.mark.parametrize("sub", ["create", "position", "review", "link"])
def test_subcommand_help(sub):
    r = _invoke([sub, "--help"])
    assert r.exit_code == 0


# ────────── flag → request body ──────────

def test_create_sends_issue(captured):
    captured.responses["/v4/cards"] = {"status": "ok", "card_id": "card_x"}
    r = _invoke(["create", "--issue", "Which db?"])
    assert r.exit_code == 0, r.output
    assert captured.calls[0] == ("POST", "/v4/cards", {"issue": "Which db?"})
    assert "card_x" in r.output


def test_create_with_card_id(captured):
    captured.responses["/v4/cards"] = {"status": "ok", "card_id": "card_x"}
    _invoke(["create", "--issue", "q", "--card_id", "card_x"])
    assert captured.calls[0][2] == {"issue": "q", "card_id": "card_x"}


def test_position_single_source_in_sources_list(captured):
    captured.responses["/positions"] = {"status": "ok", "card_id": "card_c", "position": "p1"}
    r = _invoke(["position", "--card", "card_c", "--claim", "SQLite",
                 "--source", "sess-abc:1-3", "--scope", "single node"])
    assert r.exit_code == 0, r.output
    method, path, body = captured.calls[0]
    assert path == "/v4/cards/card_c/positions"
    assert body["claim"] == "SQLite" and body["scope"] == "single node"
    assert body["sources"] == [{"session_id": "sess-abc", "indexes": "1-3"}]
    assert "p1" in r.output and "card_c#p1" in r.output


def test_position_all_sources_ride_in_create(captured):
    # All --source go in the single position-create call (no overflow POST
    # to .../sessions — that endpoint was removed).
    captured.responses["/positions"] = {"status": "ok", "card_id": "card_c", "position": "p1"}
    _invoke(["position", "--card", "card_c", "--claim", "x",
             "--source", "sess-a:1", "--source", "sess-b:2"])
    assert len(captured.calls) == 1
    method, path, body = captured.calls[0]
    assert path == "/v4/cards/card_c/positions"
    assert body["sources"] == [
        {"session_id": "sess-a", "indexes": "1"},
        {"session_id": "sess-b", "indexes": "2"},
    ]
    # no call to a /sessions endpoint
    assert not any(c[1].endswith("/sessions") for c in captured.calls)


def test_review_position_target(captured):
    captured.responses["/reviews"] = {"status": "ok", "review_id": "review_r",
                                      "target": "card_c#p1", "target_kind": "position",
                                      "argument": 1}
    _invoke(["review", "--target", "card_c#p1", "--argument", "+1", "--cite", "sess-a:2"])
    method, path, body = captured.calls[0]
    assert path == "/v4/cards/card_c/positions/p1/reviews"
    assert body["argument"] == 1 and body["session_id"] == "sess-a" and body["indexes"] == "2"
    assert body["target"] == "card_c#p1"


def test_review_link_target_routes_to_links(captured):
    captured.responses["/reviews"] = {"status": "ok", "review_id": "review_r",
                                      "target": "card_c#l2", "target_kind": "link",
                                      "argument": -1}
    _invoke(["review", "--target", "card_c#l2", "--argument", "-1", "--cite", "sess-a:3"])
    method, path, body = captured.calls[0]
    assert path == "/v4/cards/card_c/links/l2/reviews"
    assert body["argument"] == -1


def test_review_rejects_non_fragment_target():
    r = _invoke(["review", "--target", "card_c", "--argument", "+1", "--cite", "sess-a:2"])
    assert r.exit_code != 0


def test_link_body_with_claim(captured):
    captured.responses["/links"] = {"status": "ok", "card_id": "card_a", "link": "l1",
                                    "type": "specializes", "target_id": "card_b",
                                    "target_type": "card", "claim": "b narrows a"}
    r = _invoke(["link", "--card", "card_a", "--type", "specializes",
                 "--target", "card_b", "--claim", "b narrows a"])
    assert captured.calls[0][2] == {"card_id": "card_a", "type": "specializes",
                                    "target_id": "card_b", "claim": "b narrows a"}
    assert "l1" in r.output


def test_link_with_sources(captured):
    captured.responses["/links"] = {"status": "ok", "card_id": "card_a", "link": "l1",
                                    "type": "specializes", "target_id": "card_b",
                                    "target_type": "card", "claim": "why"}
    _invoke(["link", "--card", "card_a", "--type", "specializes",
             "--target", "card_b", "--claim", "why",
             "--source", "sess-a:1-2", "--source", "sess-b:7"])
    body = captured.calls[0][2]
    assert body["source"] == [
        {"session_id": "sess-a", "indexes": "1-2"},
        {"session_id": "sess-b", "indexes": "7"},
    ]


# ────────── parsing helpers ──────────

def test_parse_source_splits_on_last_colon():
    assert _parse_source("sess-abc:11-15") == ("sess-abc", "11-15")
    assert _parse_source("sess-abc:3,7,12") == ("sess-abc", "3,7,12")


def test_parse_source_rejects_missing_colon():
    import click
    with pytest.raises(click.BadParameter):
        _parse_source("sess-abc")


def test_read_text_arg_file(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("multi\nline `claim`")
    assert _read_text_arg(f"@{p}") == "multi\nline `claim`"
    assert _read_text_arg("inline") == "inline"


# ────────── formatters ──────────

def test_fmt_read_card_stars_current_answer():
    out = card_mod._fmt_read({"type": "card", "card": {
        "card_id": "card_x", "issue": "Q?",
        "positions": [
            {"id": "card_x#p2", "position": "p2", "claim": "A", "credence": 2,
             "up_count": 2, "down_count": 0, "neutral_count": 0, "scope": "ctx"},
            {"id": "card_x#p1", "position": "p1", "claim": "B", "credence": -1,
             "up_count": 0, "down_count": 1, "neutral_count": 0, "scope": ""},
        ],
        "links": [{"dir": "out", "type": "specializes", "target_id": "card_y",
                   "target_type": "card", "claim": "y narrows x", "credence": 1}],
        "sessions": [{"session_id": "sess-a"}],
    }})
    assert "★" in out and "card_x#p2" in out and "credence +2" in out
    assert "specializes" in out and "sess-a" in out and "y narrows x" in out


def test_fmt_read_link():
    out = card_mod._fmt_read({"type": "link", "link": {
        "id": "card_x#l1", "link": "l1", "card_id": "card_x", "type": "specializes",
        "target_id": "card_y", "claim": "why", "credence": -1,
        "up_count": 0, "down_count": 1, "neutral_count": 0,
        "reviews": [{"argument": -1, "session_id": "sess-a", "indexes": "1"}],
    }})
    assert "card_x#l1" in out and "credence -1" in out and "why" in out


def test_fmt_search_renders_q_and_a():
    out = card_mod._fmt_search({"query": "db", "total": 1, "returned": 1, "cards": [
        {"card_id": "card_x", "issue": "Which db?", "position_count": 1,
         "top_position": {"claim": "SQLite", "credence": 1}},
    ]})
    assert "**Q:** Which db?" in out and "**A:** SQLite" in out


def test_fmt_search_renders_mixed_kinds():
    out = card_mod._fmt_search({"query": "lancedb", "total": 3, "returned": 3, "cards": [
        {"kind": "card", "card_id": "card_x", "issue": "Which db?",
         "position_count": 1, "top_position": {"claim": "SQLite", "credence": 1}},
        {"kind": "insight", "insight_id": "insight_y", "insight": "use embedded vecdb"},
        {"kind": "session", "session_id": "sess-z", "source": "claude-code",
         "hit_count": 2, "hits": [{"index": 3, "role": "human", "text": "lancedb rocks"}]},
    ]})
    assert "[CARD]" in out and "[INSIGHT]" in out and "[SESSION]" in out
    assert "use embedded vecdb" in out
    assert "sess-z" in out and "lancedb rocks" in out


def test_fmt_read_session_renders_rounds():
    out = card_mod._fmt_read({"type": "session", "session": {
        "session_id": "sess-abc", "source": "claude-code",
        "created_at": "2026-06-19T00:00:00Z",
        "rounds": [
            {"index": 1, "role": "human", "speaker": "user",
             "content": [{"type": "text", "text": "what is lancedb?"}]},
            {"index": 2, "role": "assistant",
             "content": [{"type": "text", "text": "an embedded vector db"}]},
        ],
    }})
    # Not just the title — the rounds' text is rendered.
    assert "sess-abc" in out
    assert "what is lancedb?" in out and "an embedded vector db" in out
    assert "2 rounds" in out and "[#1]" in out and "[#2]" in out


def test_fmt_read_session_non_text_block_placeholder():
    out = card_mod._fmt_read({"type": "session", "session": {
        "session_id": "sess-tool", "source": "claude-code",
        "rounds": [
            {"index": 1, "role": "assistant",
             "content": [{"type": "tool_use", "name": "bash"}]},
        ],
    }})
    assert "_(tool_use)_" in out


# ────────── read mark fragment (sess_…#m<n>) ──────────

def test_fmt_read_mark_renders_body_and_issues():
    out = card_mod._fmt_read({
        "type": "mark", "id": "sess-abc#m1",
        "session_id": "sess-abc", "mark_seq": "m1",
        "mark": {
            "description": "reading the pty/tmux stretch",
            "last_index": 5,
            "mark": "user pivoted. #why does pty remind of tmux？",
            "indexes": "3-4",
            "issues": [
                {"issue": "why does pty remind of tmux", "card_id": "card_01",
                 "is_new": True, "indexes": "3-4"},
            ],
            "created_at": "2026-06-19T00:00:00Z",
        },
    })
    # Header carries the address, not the (empty) fallback.
    assert out != "（empty）"
    assert "# mark · `sess-abc#m1`" in out
    assert "reading the pty/tmux stretch" in out          # description/scenario
    assert "#why does pty remind of tmux？" in out          # the mark text
    assert "3-4" in out                                    # indexes
    assert "## issues (1)" in out
    assert "new card" in out and "card_01" in out          # issue → new card


def test_fmt_read_mark_no_issues():
    out = card_mod._fmt_read({
        "type": "mark", "id": "sess-abc#m2",
        "mark": {"description": "triage", "last_index": 5,
                 "mark": "just EMFILE triage, no question.", "issues": []},
    })
    assert "# mark · `sess-abc#m2`" in out
    assert "## issues (0)" in out
    assert "no #…？ issues" in out


# ────────── session read folds in marks ──────────

def test_fmt_read_session_renders_marks_section():
    out = card_mod._fmt_read({"type": "session", "session": {
        "session_id": "sess-abc", "source": "claude-code",
        "rounds": [
            {"index": 1, "role": "human",
             "content": [{"type": "text", "text": "hi"}]},
        ],
        "marks": [
            {"mark": "m1", "description": "scene", "text": "#a question？",
             "indexes": "1", "issues": [
                 {"issue": "a question", "card_id": "card_07",
                  "is_new": True, "indexes": "1"}]},
            {"mark": "m2", "description": "scene", "text": "no question here",
             "indexes": None, "issues": []},
        ],
    }})
    assert "## marks (2)" in out
    assert "`m1`" in out and "`m2`" in out
    assert "card_07" in out and "new" in out
    assert "no issues" in out                              # m2 has none


def test_fmt_read_session_no_marks_section_when_empty():
    out = card_mod._fmt_read({"type": "session", "session": {
        "session_id": "sess-abc", "source": "claude-code",
        "rounds": [
            {"index": 1, "role": "human",
             "content": [{"type": "text", "text": "hi"}]},
        ],
        "marks": [],
    }})
    # 0 marks → renders fine, no marks section.
    assert "## marks" not in out
    assert "hi" in out

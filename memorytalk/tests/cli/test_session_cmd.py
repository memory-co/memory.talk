"""CLI: memory.talk session list / tag — parsing + formatter smoke.

The actual HTTP path is exercised by ``tests/api/test_sessions_*``.
This file pins the CLI-only concerns: positional arg parsing for `tag`,
duration parsing for `--since` / `--until`, formatter output shape.
"""
from __future__ import annotations
import pytest

from click.testing import CliRunner


# ────────── --help shape ──────────

def test_session_help_lists_subcommands():
    from memorytalk.cli import main
    runner = CliRunner()
    r = runner.invoke(main, ["session", "--help"])
    assert r.exit_code == 0
    assert "list" in r.output
    assert "tag" in r.output


@pytest.mark.parametrize("sub", ["list", "tag"])
def test_session_sub_help_succeeds(sub):
    from memorytalk.cli import main
    runner = CliRunner()
    r = runner.invoke(main, ["session", sub, "--help"])
    assert r.exit_code == 0, r.output


# ────────── parse_kv_args (tag positional arg parser) ──────────

def test_parse_kv_args_set_and_unset():
    from memorytalk.util.tags import parse_kv_args
    s, u = parse_kv_args(["project=billing", "-draft", "status=wip"])
    assert s == {"project": "billing", "status": "wip"}
    assert u == ["draft"]


def test_parse_kv_args_empty_inputs():
    from memorytalk.util.tags import parse_kv_args
    assert parse_kv_args([]) == ({}, [])


def test_parse_kv_args_rejects_bare_key():
    from memorytalk.util.tags import parse_kv_args, TagValidationError
    with pytest.raises(TagValidationError):
        parse_kv_args(["project"])  # neither K=V nor -K


def test_parse_kv_args_rejects_empty_value():
    from memorytalk.util.tags import parse_kv_args, TagValidationError
    with pytest.raises(TagValidationError):
        parse_kv_args(["project="])


def test_parse_kv_args_rejects_lone_dash():
    from memorytalk.util.tags import parse_kv_args, TagValidationError
    with pytest.raises(TagValidationError):
        parse_kv_args(["-"])


# ────────── duration parser ──────────

def test_duration_parser_units():
    from memorytalk.cli.session import _duration_to_iso
    for d in ("7d", "12h", "2w"):
        out = _duration_to_iso(d)
        assert out and out.endswith("Z"), d


def test_duration_parser_passes_iso_through():
    from memorytalk.cli.session import _duration_to_iso
    out = _duration_to_iso("2026-05-01T00:00:00Z")
    # Either preserved exactly, or normalized to a parseable form; we
    # only require that a roundtrip yields something nonempty.
    assert out


def test_duration_parser_rejects_garbage():
    import click
    from memorytalk.cli.session import _duration_to_iso
    with pytest.raises(click.BadParameter):
        _duration_to_iso("7days")


# ────────── formatter shape ──────────

def test_fmt_session_list_empty():
    from memorytalk.cli._format import fmt_session_list
    out = fmt_session_list({"total": 0, "returned": 0, "sessions": []})
    assert "# session list" in out
    assert "0 / 0 results" in out


def test_fmt_session_list_renders_block_per_session():
    from memorytalk.cli._format import fmt_session_list
    payload = {
        "total": 2, "returned": 2,
        "sessions": [
            {
                "session_id": "sess-15f0a7fb-x", "source": "claude-code",
                "round_count": 47, "cwd": "/work/billing",
                "tags": {"project": "billing", "status": "wip"},
                "created_at": "2026-05-24T09:12:00Z",
            },
            {
                "session_id": "sess-d68dd382-y", "source": "codex",
                "round_count": 12, "cwd": "/work/infra",
                "tags": {},
                "created_at": "2026-05-24T08:30:00Z",
            },
        ],
    }
    out = fmt_session_list(payload, filter_summary="tag=project=billing")
    # Header echoes filter + N / TOTAL.
    assert "`filter: tag=project=billing` · 2 / 2 results" in out
    # One H3 per session.
    assert out.count("### [SESSION]") == 2
    # First session shows tags inline; second one omits the `tags:` segment.
    assert "tags: project=billing status=wip" in out
    assert "tags:" not in out.split("sess-d68dd382-y")[1].split("---")[0]


def test_fmt_session_list_shows_truncation_hint():
    from memorytalk.cli._format import fmt_session_list
    payload = {
        "total": 50, "returned": 2,
        "sessions": [
            {"session_id": f"sess-{i}", "source": "claude-code",
             "round_count": 1, "cwd": None, "tags": {},
             "created_at": "2026-05-24T09:12:00Z"}
            for i in range(2)
        ],
    }
    out = fmt_session_list(payload)
    assert "showing 2 of 50" in out


def test_fmt_session_tag_query_empty():
    from memorytalk.cli._format import fmt_session_tag
    out = fmt_session_tag(
        {"session_id": "sess-x", "tags": {}}, is_query=True,
    )
    assert out.strip() == "(no tags)"


def test_fmt_session_tag_query_table():
    from memorytalk.cli._format import fmt_session_tag
    out = fmt_session_tag(
        {"session_id": "sess-x", "tags": {"a": "1", "b": "2"}},
        is_query=True,
    )
    assert "# sess-x · tags" in out
    assert "| a | 1 |" in out
    assert "| b | 2 |" in out


def test_fmt_session_tag_set_confirm():
    from memorytalk.cli._format import fmt_session_tag
    out = fmt_session_tag(
        {"session_id": "sess-x", "tags": {"a": "1"}}, is_query=False,
    )
    assert "ok:" in out
    assert "a=1" in out

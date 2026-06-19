"""CLI: memory.talk insight {search, view} — read-only old card surface.

Insight is read-only in v4: only search (list/filter via GET /v4/insights)
and view (POST /v4/read) survive. This pins the CLI surface (help, wiring,
formatter shape).
"""
from __future__ import annotations
import json as _json

import pytest

from click.testing import CliRunner


def test_insight_group_lists_subcommands():
    from memorytalk.cli import main
    runner = CliRunner()
    r = runner.invoke(main, ["insight", "--help"])
    assert r.exit_code == 0
    # Commands listed in click's "Commands:" section, one per line.
    cmd_lines = [ln.strip().split(" ")[0] for ln in r.output.splitlines()
                 if ln.startswith("  ") and ln.strip()]
    assert "search" in cmd_lines
    assert "view" in cmd_lines
    # write subcommands are gone
    for gone in ("create", "delete", "tag", "list"):
        assert gone not in cmd_lines


@pytest.mark.parametrize("sub", ["search", "view"])
def test_insight_subcommand_help_succeeds(sub):
    from memorytalk.cli import main
    runner = CliRunner()
    r = runner.invoke(main, ["insight", sub, "--help"])
    assert r.exit_code == 0, r.output


# ────────── insight search wiring ──────────

def test_insight_search_hits_v4_insights(monkeypatch):
    calls: list[tuple[str, str]] = []

    def _fake_api(method, path, cfg, json_body=None, timeout=30.0, params=None):
        calls.append((method, path))
        return {"total": 0, "returned": 0, "cards": []}

    from memorytalk.cli import insight as insight_mod
    monkeypatch.setattr(insight_mod, "api", _fake_api)

    from memorytalk.cli import main
    runner = CliRunner()
    r = runner.invoke(main, ["insight", "search", "--tag", "project=x", "--json"])
    assert r.exit_code == 0, r.output
    assert calls == [("GET", "/v4/insights")]


# ────────── insight view wiring ──────────

def test_insight_view_hits_v4_read(monkeypatch):
    calls: list[tuple[str, str, dict]] = []

    def _fake_api(method, path, cfg, json_body=None, timeout=30.0, params=None):
        calls.append((method, path, json_body))
        return {"type": "insight", "read_at": "t",
                "insight": {"insight_id": "insight_x", "insight": "hi",
                            "rounds": [], "stats": {}}}

    from memorytalk.cli import insight as insight_mod
    monkeypatch.setattr(insight_mod, "api", _fake_api)

    from memorytalk.cli import main
    runner = CliRunner()
    r = runner.invoke(main, ["insight", "view", "insight_x", "--json"])
    assert r.exit_code == 0, r.output
    assert calls == [("POST", "/v4/read", {"id": "insight_x"})]


# ────────── fmt_insight_list ──────────

def test_fmt_insight_list_empty():
    from memorytalk.cli._format import fmt_insight_list
    out = fmt_insight_list({"total": 0, "returned": 0, "cards": []})
    assert "0 / 0 results" in out


def test_fmt_insight_list_renders_block_per_insight():
    from memorytalk.cli._format import fmt_insight_list
    payload = {
        "total": 2, "returned": 2,
        "cards": [
            {
                "insight_id": "insight_01abc", "insight": "LanceDB picked",
                "created_at": "2026-05-24T09:12:00Z",
                "tags": {"project": "billing", "status": "verified"},
                "stats": {
                    "review_up": 7, "review_down": 3, "review_neutral": 2,
                    "review_count": 12, "read_count": 42, "recall_count": 18,
                },
            },
            {
                "insight_id": "insight_01def", "insight": "no-tag insight",
                "created_at": "2026-05-23T14:21:00Z",
                "tags": {},
                "stats": {
                    "review_up": 0, "review_down": 0, "review_neutral": 0,
                    "review_count": 0, "read_count": 0, "recall_count": 0,
                },
            },
        ],
    }
    out = fmt_insight_list(payload, filter_summary="tag=project=billing")
    assert "`filter: tag=project=billing` · 2 / 2 results" in out
    assert out.count("### [INSIGHT]") == 2
    assert "↑7 ↓3 · reviews 12 · reads 42 · recalls 18" in out
    assert "LanceDB picked" in out
    assert "tags: project=billing status=verified" in out
    second_block = out.split("insight_01def")[1].split("---")[0]
    assert "tags:" not in second_block


def test_fmt_insight_list_truncation_hint():
    from memorytalk.cli._format import fmt_insight_list
    payload = {
        "total": 50, "returned": 2,
        "cards": [
            {"insight_id": f"insight_{i}", "insight": "x",
             "created_at": "2026-05-24T09:12:00Z",
             "tags": {}, "stats": {}}
            for i in range(2)
        ],
    }
    out = fmt_insight_list(payload)
    assert "showing 2 of 50" in out


# ────────── fmt_read renders insight (read-only) ──────────

def test_fmt_read_renders_insight():
    from memorytalk.cli.card import _fmt_read
    out = _fmt_read({
        "type": "insight",
        "insight": {"insight_id": "insight_x", "insight": "the claim",
                    "rounds": [], "stats": {"read_count": 3}},
    })
    assert "insight_x" in out
    assert "the claim" in out

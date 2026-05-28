"""CLI: memory.talk card {create, list, tag} — help shape + formatter smoke.

HTTP behavior is covered by tests/api/test_cards_list.py +
tests/api/test_cards_tag.py — this file pins the CLI surface only
(help text, parsing wiring, formatter output shape).
"""
from __future__ import annotations
import pytest

from click.testing import CliRunner


def test_card_group_lists_subcommands():
    from memorytalk.cli import main
    runner = CliRunner()
    r = runner.invoke(main, ["card", "--help"])
    assert r.exit_code == 0
    for sub in ("create", "list", "tag"):
        assert sub in r.output


@pytest.mark.parametrize("sub", ["create", "list", "tag"])
def test_card_subcommand_help_succeeds(sub):
    from memorytalk.cli import main
    runner = CliRunner()
    r = runner.invoke(main, ["card", sub, "--help"])
    assert r.exit_code == 0, r.output


def test_old_card_json_form_is_gone():
    """0.7.x's bare ``card '<json>'`` was hard-renamed in 0.8.x. The
    second positional arg should now be interpreted as a subcommand
    name — `card '{"insight":"..."}'` → unknown subcommand → exit 2."""
    from memorytalk.cli import main
    runner = CliRunner()
    r = runner.invoke(main, ["card", '{"insight":"x"}'])
    assert r.exit_code != 0


# ────────── fmt_card_list ──────────

def test_fmt_card_list_empty():
    from memorytalk.cli._format import fmt_card_list
    out = fmt_card_list({"total": 0, "returned": 0, "cards": []})
    assert "# card list" in out
    assert "0 / 0 results" in out


def test_fmt_card_list_renders_block_per_card():
    from memorytalk.cli._format import fmt_card_list
    payload = {
        "total": 2, "returned": 2,
        "cards": [
            {
                "card_id": "card_01abc", "insight": "LanceDB picked",
                "created_at": "2026-05-24T09:12:00Z",
                "tags": {"project": "billing", "status": "verified"},
                "stats": {
                    "review_up": 7, "review_down": 3, "review_neutral": 2,
                    "review_count": 12, "read_count": 42, "recall_count": 18,
                },
            },
            {
                "card_id": "card_01def", "insight": "no-tag card",
                "created_at": "2026-05-23T14:21:00Z",
                "tags": {},
                "stats": {
                    "review_up": 0, "review_down": 0, "review_neutral": 0,
                    "review_count": 0, "read_count": 0, "recall_count": 0,
                },
            },
        ],
    }
    out = fmt_card_list(payload, filter_summary="tag=project=billing")
    # Header echoes filter + counts.
    assert "`filter: tag=project=billing` · 2 / 2 results" in out
    # One H3 per card.
    assert out.count("### [CARD]") == 2
    # Inline stats formatted as documented.
    assert "↑7 ↓3 · reviews 12 · reads 42 · recalls 18" in out
    # Insight rendered as a paragraph.
    assert "LanceDB picked" in out
    # First card has tags inline; second card has no tags segment.
    assert "tags: project=billing status=verified" in out
    second_block = out.split("card_01def")[1].split("---")[0]
    assert "tags:" not in second_block


def test_fmt_card_list_truncation_hint():
    from memorytalk.cli._format import fmt_card_list
    payload = {
        "total": 50, "returned": 2,
        "cards": [
            {"card_id": f"card_{i}", "insight": "x",
             "created_at": "2026-05-24T09:12:00Z",
             "tags": {}, "stats": {}}
            for i in range(2)
        ],
    }
    out = fmt_card_list(payload)
    assert "showing 2 of 50" in out


# ────────── fmt_card_tag ──────────

def test_fmt_card_tag_query_empty():
    from memorytalk.cli._format import fmt_card_tag
    out = fmt_card_tag(
        {"card_id": "card_x", "tags": {}}, is_query=True,
    )
    assert out.strip() == "(no tags)"


def test_fmt_card_tag_query_table():
    from memorytalk.cli._format import fmt_card_tag
    out = fmt_card_tag(
        {"card_id": "card_x", "tags": {"a": "1", "b": "2"}}, is_query=True,
    )
    assert "# card_x · tags" in out
    assert "| a | 1 |" in out


def test_fmt_card_tag_set_confirm():
    from memorytalk.cli._format import fmt_card_tag
    out = fmt_card_tag(
        {"card_id": "card_x", "tags": {"a": "1"}}, is_query=False,
    )
    assert "ok:" in out
    assert "a=1" in out

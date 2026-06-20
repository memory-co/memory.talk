"""`#…？` issue extraction — the seam that turns marks into cards."""
from __future__ import annotations

import pytest

from memorytalk.util.marks import parse_issues


def test_single_fullwidth_issue():
    text = "配 pty 时用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？他其实想要可重连会话。"
    assert parse_issues(text) == ["为什么 pty 会让用户想到 tmux"]


def test_halfwidth_terminator_accepted():
    assert parse_issues("#why pty? answer") == ["why pty"]


def test_multiple_issues_in_one_mark():
    assert parse_issues("a #q1? b #q2？ c") == ["q1", "q2"]


def test_no_issue_when_hash_unterminated():
    assert parse_issues("no issue here # just a hash, ends here") == []


def test_hash_binds_to_first_terminator_spanning_inner_hash():
    # Spec rule is "# up to the FIRST ？": the first '#' wins and its body
    # runs to the first terminator (swallowing an inner literal '#').
    assert parse_issues("#outer then #inner？ tail") == ["outer then #inner"]


def test_unterminated_trailing_hash_is_not_an_issue():
    # A '#' with NO terminator anywhere after it is literal prose.
    assert parse_issues("issue one #q？ then a loose # with no terminator") == ["q"]


def test_empty_body_dropped():
    assert parse_issues("#？ #?  ") == []


def test_nearest_terminator_wins():
    # The '#' closes at the FIRST terminator, not a later one.
    assert parse_issues("#short？ then more?") == ["short"]


def test_body_is_trimmed():
    assert parse_issues("#   spaced out   ？") == ["spaced out"]


@pytest.mark.parametrize("bad", ["", None, 123])
def test_non_string_or_empty_returns_empty(bad):
    assert parse_issues(bad) == []


def test_terminator_not_reused_across_two_issues():
    # Two separate issues, each with its own terminator.
    assert parse_issues("#a？#b？") == ["a", "b"]

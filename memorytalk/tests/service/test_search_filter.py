"""Unit tests for the per-type strong-floor filter in search service."""
from __future__ import annotations

from memorytalk.service.search import (
    _CARD_STRONG_FLOOR, _SESSION_STRONG_FLOOR, _apply_strong_floor,
)


def _c(score: float) -> tuple[str, dict]:
    return ("card", {"final_score": score})


def _s(score: float) -> tuple[str, dict]:
    return ("session", {"final_score": score})


class TestStrongFloor:
    def test_no_filter_when_all_below_floor_per_type(self):
        # Nothing reaches the floor in either type → keep all.
        merged = [_s(0.015), _s(0.010), _c(0.05), _c(0.02)]
        kept = _apply_strong_floor(merged)
        assert kept == merged

    def test_filters_weak_sessions_when_strong_exists(self):
        # One session ≥ 0.02 → drop the weak ones; cards untouched (no
        # cards present).
        strong = _s(0.025)
        weak1 = _s(0.015)
        weak2 = _s(0.010)
        kept = _apply_strong_floor([strong, weak1, weak2])
        assert kept == [strong]

    def test_filters_weak_cards_when_strong_card_exists(self):
        # One card ≥ 0.1 → drop weak cards.
        strong = _c(0.5)  # heavily reviewed
        weak = _c(0.03)  # just RRF, no stats
        kept = _apply_strong_floor([strong, weak])
        assert kept == [strong]

    def test_per_type_independence(self):
        # Strong session + only weak cards → keep all cards (no strong
        # card to filter against), drop weak sessions.
        strong_sess = _s(0.025)
        weak_sess = _s(0.010)
        weak_card1 = _c(0.05)
        weak_card2 = _c(0.04)
        merged = [strong_sess, weak_sess, weak_card1, weak_card2]
        kept = _apply_strong_floor(merged)
        # cards: no one cleared the floor → keep all
        assert weak_card1 in kept
        assert weak_card2 in kept
        # sessions: strong exists → only strong
        assert strong_sess in kept
        assert weak_sess not in kept

    def test_preserves_original_order(self):
        # Filter returns survivors in input order — caller sorted by
        # final_score before calling us.
        a = _c(0.5)
        b = _s(0.025)
        c = _c(0.3)
        d = _s(0.020)
        e = _c(0.05)  # dropped (cards floor 0.1)
        f = _s(0.015)  # dropped (sessions floor 0.02)
        kept = _apply_strong_floor([a, b, c, d, e, f])
        assert kept == [a, b, c, d]

    def test_empty_input(self):
        assert _apply_strong_floor([]) == []

    def test_only_one_type_present(self):
        # No card candidates at all — session logic still works.
        merged = [_s(0.03), _s(0.01)]
        kept = _apply_strong_floor(merged)
        assert kept == [_s(0.03)] or (
            len(kept) == 1 and kept[0][1]["final_score"] == 0.03
        )

    def test_floor_values_match_constants(self):
        # Pin the floor constants — changing them in source should make
        # this test fail visibly, forcing a docs / changelog review.
        assert _SESSION_STRONG_FLOOR == 0.02
        assert _CARD_STRONG_FLOOR == 0.1

"""Search session render — adjacent-hit merging.

Server returns hits sorted by score (not by index); the CLI clusters
hits whose context windows overlap so the same round isn't rendered
twice across consecutive fences. See ``_merge_hits`` / ``_fmt_hit_group``
in ``memorytalk.cli._format``.
"""
from __future__ import annotations

from memorytalk.cli._format import (
    _fmt_search_session, _merge_hits,
)


def _hit(idx: int, role: str, text: str, score: float,
         ctx_before_idx: int | None = None,
         ctx_after_idx: int | None = None) -> dict:
    """Build a minimal hit dict with adjacent indices for context."""
    h: dict = {
        "index": idx, "role": role, "text": text, "score": score,
    }
    if ctx_before_idx is not None:
        h["context_before"] = {
            "index": ctx_before_idx, "role": "assistant",
            "text": f"ctx{ctx_before_idx}",
        }
    if ctx_after_idx is not None:
        h["context_after"] = {
            "index": ctx_after_idx, "role": "assistant",
            "text": f"ctx{ctx_after_idx}",
        }
    return h


class TestMergeHits:
    """Pure unit tests over the grouping helper."""

    def test_empty(self):
        assert _merge_hits([]) == []

    def test_single_hit_is_its_own_group(self):
        h = _hit(5, "human", "x", 0.03)
        groups = _merge_hits([h])
        assert groups == [[h]]

    def test_two_adjacent_hits_merge(self):
        h4 = _hit(4, "human", "q", 0.03, 3, 5)
        h5 = _hit(5, "assistant", "a", 0.02, 4, 6)
        groups = _merge_hits([h4, h5])
        assert len(groups) == 1
        # Order inside a group is index ascending.
        assert [h["index"] for h in groups[0]] == [4, 5]

    def test_three_chained_hits_merge(self):
        # 10 ↔ 11 ↔ 12 — chained, all in one group.
        hs = [
            _hit(10, "human", "a", 0.03, 9, 11),
            _hit(11, "assistant", "b", 0.025, 10, 12),
            _hit(12, "tool", "c", 0.02, 11, 13),
        ]
        groups = _merge_hits(hs)
        assert len(groups) == 1
        assert [h["index"] for h in groups[0]] == [10, 11, 12]

    def test_touching_through_shared_context(self):
        # idx diff = 2: hit at 4's ctx_after is round 5, hit at 6's
        # ctx_before is also round 5 — they touch through a shared
        # context round.
        h4 = _hit(4, "human", "h4", 0.03, 3, 5)
        h6 = _hit(6, "human", "h6", 0.02, 5, 7)
        groups = _merge_hits([h4, h6])
        assert len(groups) == 1
        assert [h["index"] for h in groups[0]] == [4, 6]

    def test_far_apart_stay_separate(self):
        # idx diff = 17 → windows don't touch → two groups.
        h3 = _hit(3, "human", "p1", 0.03, 2, 4)
        h20 = _hit(20, "human", "p2", 0.02, 19, 21)
        groups = _merge_hits([h3, h20])
        assert len(groups) == 2
        # Strongest group first.
        assert groups[0][0]["index"] == 3
        assert groups[1][0]["index"] == 20

    def test_input_sorted_by_score_not_index(self):
        # API sorts hits by score desc; merging must still cluster by
        # adjacency, then re-emit groups sorted by top score.
        weak = _hit(4, "human", "q", 0.02, 3, 5)
        strong = _hit(5, "assistant", "a", 0.09, 4, 6)
        groups = _merge_hits([strong, weak])  # input order = score desc
        assert len(groups) == 1
        assert [h["index"] for h in groups[0]] == [4, 5]

    def test_groups_sorted_by_top_score_desc(self):
        # Two non-overlapping groups, weaker by index but stronger by
        # score — score order wins for group sequencing.
        far_strong = _hit(3, "human", "p1", 0.5, 2, 4)
        near_weak = _hit(20, "human", "p2", 0.01, 19, 21)
        groups = _merge_hits([near_weak, far_strong])  # input shuffled
        assert groups[0][0]["index"] == 3  # strong first
        assert groups[1][0]["index"] == 20


class TestFmtSearchSessionMerge:
    """End-to-end rendering — confirm the merged fence shape."""

    def test_single_hit_unchanged_layout(self):
        # No adjacency → header reads "score" (not "top score").
        entry = {
            "session_id": "s", "source": "cc", "hit_count": 1,
            "hits": [_hit(5, "human", "q", 0.03, 4, 6)],
        }
        out = _fmt_search_session(entry)
        assert "**#5** · score `0.0300`" in out
        # ``top score`` only appears when there's more than one hit
        # in a group.
        assert "top score" not in out

    def test_adjacent_hits_merged_into_one_fence(self):
        # Reproduces the example from the design discussion.
        entry = {
            "session_id": "s", "source": "cc", "hit_count": 2,
            "hits": [
                {"index": 4, "role": "human", "text": "q", "score": 0.0309,
                 "context_before": {"index": 3, "role": "human", "text": "pre"},
                 "context_after":  {"index": 5, "role": "assistant", "text": "a"}},
                {"index": 5, "role": "assistant", "text": "a", "score": 0.0159,
                 "context_before": {"index": 4, "role": "human", "text": "q"},
                 "context_after":  {"index": 6, "role": "assistant", "text": "post"}},
            ],
        }
        out = _fmt_search_session(entry)
        # Header lists both indices, anchors on top score.
        assert "**#4, #5** · top score `0.0309`" in out
        # Body contains rounds 3..6 with hits 4 and 5 both marked.
        assert "[3 HUMAN] pre" in out
        assert "[4 HUMAN*] q" in out
        assert "[5 AI*] a" in out
        assert "[6 AI] post" in out
        # Each round appears exactly once (no duplication across two
        # fences like the un-merged layout would produce).
        assert out.count("[5 AI*] a") == 1
        # Only one fence block per group.
        assert out.count("```") == 2

    def test_three_hit_group_all_marked(self):
        entry = {
            "session_id": "s", "source": "cc", "hit_count": 3,
            "hits": [
                _hit(10, "human", "a", 0.03, 9, 11),
                _hit(11, "assistant", "b", 0.025, 10, 12),
                _hit(12, "tool", "c", 0.02, 11, 13),
            ],
        }
        out = _fmt_search_session(entry)
        assert "**#10, #11, #12**" in out
        assert "[10 HUMAN*]" in out
        assert "[11 AI*]" in out
        assert "[12 TOOL*]" in out
        # Bracketing context rounds (no *).
        assert "[9 AI] ctx9" in out
        assert "[13 AI] ctx13" in out

    def test_far_apart_render_independently(self):
        entry = {
            "session_id": "s", "source": "cc", "hit_count": 2,
            "hits": [
                _hit(3, "human", "p1", 0.03, 2, 4),
                _hit(20, "human", "p2", 0.02, 19, 21),
            ],
        }
        out = _fmt_search_session(entry)
        # Two separate fences, no merge header.
        assert "top score" not in out
        # Each has its own block.
        assert out.count("**#3** · score") == 1
        assert out.count("**#20** · score") == 1
        # Six fence markers total — three pairs (well, two pairs of
        # opener+closer, four backtick rows).
        assert out.count("```") == 4

    def test_hit_text_wins_over_context_text_on_collision(self):
        # When the same round appears as a hit in one entry and as a
        # context in another's window, hit version should be rendered
        # (richer snippet). Easiest to assert via the role marker:
        # only the hit version gets ``*``.
        entry = {
            "session_id": "s", "source": "cc", "hit_count": 2,
            "hits": [
                {"index": 4, "role": "human", "text": "hit-text-4",
                 "score": 0.03,
                 "context_before": None,
                 "context_after": {"index": 5, "role": "assistant",
                                   "text": "ctx-version-of-5"}},
                {"index": 5, "role": "assistant", "text": "hit-text-5",
                 "score": 0.02,
                 "context_before": {"index": 4, "role": "human",
                                    "text": "ctx-version-of-4"},
                 "context_after": None},
            ],
        }
        out = _fmt_search_session(entry)
        # Both indices marked as hits.
        assert "[4 HUMAN*]" in out
        assert "[5 AI*]" in out
        # Hit text wins.
        assert "hit-text-4" in out and "ctx-version-of-4" not in out
        assert "hit-text-5" in out and "ctx-version-of-5" not in out

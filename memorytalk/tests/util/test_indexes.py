"""Unit tests for util/indexes.py — pure parser, no DB / no I/O."""
from __future__ import annotations
import pytest

from memorytalk.util.indexes import IndexesParseError, parse_indexes


class TestParseIndexes:
    def test_range_expands(self):
        assert parse_indexes("11-15") == [11, 12, 13, 14, 15]

    def test_single_index(self):
        assert parse_indexes("4") == [4]

    def test_list(self):
        assert parse_indexes("3,7,12") == [3, 7, 12]

    def test_mixed_range_and_list(self):
        # `"1-3,7"` → [1, 2, 3, 7]
        assert parse_indexes("1-3,7") == [1, 2, 3, 7]

    def test_one_element_range(self):
        assert parse_indexes("5-5") == [5]

    def test_reversed_range_rejected(self):
        with pytest.raises(IndexesParseError, match="monotonic"):
            parse_indexes("15-11")

    def test_unsorted_list_rejected(self):
        with pytest.raises(IndexesParseError, match="monotonic"):
            parse_indexes("12,7,3")

    def test_duplicate_in_list_rejected(self):
        # Equal adjacent values → not strictly increasing.
        with pytest.raises(IndexesParseError, match="monotonic"):
            parse_indexes("3,3")

    def test_overlapping_segments_rejected(self):
        # 1-5 then 4 → 4 appears twice in the expanded sequence.
        with pytest.raises(IndexesParseError, match="monotonic"):
            parse_indexes("1-5,4")

    def test_empty_string_rejected(self):
        with pytest.raises(IndexesParseError):
            parse_indexes("")

    def test_non_string_rejected(self):
        with pytest.raises(IndexesParseError):
            parse_indexes(None)  # type: ignore

    def test_non_integer_rejected(self):
        with pytest.raises(IndexesParseError):
            parse_indexes("foo")

    def test_non_integer_in_range_rejected(self):
        with pytest.raises(IndexesParseError):
            parse_indexes("1-bad")

    def test_empty_segment_rejected(self):
        # ``"1,,3"`` is malformed.
        with pytest.raises(IndexesParseError):
            parse_indexes("1,,3")

    def test_whitespace_in_segment_ok(self):
        # Spaces around commas / dashes are normalized via .strip() per-segment.
        assert parse_indexes(" 1 , 3 - 5 ") == [1, 3, 4, 5]

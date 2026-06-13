"""instant — 带时区解析 + last_round_update_time. See README.md."""
from __future__ import annotations

from memorytalk.util.instant import last_round_update_time


def test_offset_timestamps_compared_temporally_not_lexically():
    # 20:00+08:00 == 12:00 UTC (earlier); 13:00Z (later). Lexically the
    # +08:00 string sorts LARGER, so a string-max impl wrongly picks the
    # earlier one. Temporal max must pick 13:00Z.
    got = last_round_update_time(
        ["2026-05-20T20:00:00+08:00", "2026-05-20T13:00:00Z"],
        created_at="2026-01-01T00:00:00Z", synced_at="2026-01-01T00:00:00Z",
    )
    assert got == "2026-05-20T13:00:00Z"


def test_falls_back_to_created_at_when_no_round_timestamp():
    got = last_round_update_time(
        [None, "", "garbage"],
        created_at="2026-03-10T09:00:00Z", synced_at="2026-06-01T00:00:00Z",
    )
    assert got == "2026-03-10T09:00:00Z"


def test_falls_back_to_synced_at_when_no_created_at():
    got = last_round_update_time(
        [], created_at="", synced_at="2026-06-01T08:30:00Z",
    )
    assert got == "2026-06-01T08:30:00Z"

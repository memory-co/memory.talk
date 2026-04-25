"""util.dsl — relative time literals like `-7d` resolved against an injected NOW."""
from __future__ import annotations
from datetime import datetime, timezone

from memory_talk_v2.util.dsl import parse


NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_parse_reltime_days_ago():
    preds = parse("created_at > -7d", now=NOW)
    assert preds[0].field == "created_at"
    assert preds[0].value.startswith("2026-04-15")  # 7 days before NOW

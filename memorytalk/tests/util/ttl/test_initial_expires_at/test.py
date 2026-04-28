"""util.ttl — initial_expires_at(): now + initial seconds, ISO round-tripped."""
from __future__ import annotations
from datetime import datetime, timezone

from memory_talk_v2.util.ttl import initial_expires_at, iso_to_dt


NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_initial_expires_at_math():
    exp = initial_expires_at(3600, now=NOW)
    assert (iso_to_dt(exp) - NOW).total_seconds() == 3600

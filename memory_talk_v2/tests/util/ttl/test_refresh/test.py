"""util.ttl — refresh(): doubles remaining within cap; expired entries are not revived."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

from memory_talk_v2.util.ttl import dt_to_iso, iso_to_dt, refresh


NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_refresh_active_doubles_within_cap():
    future = dt_to_iso(NOW + timedelta(seconds=100))
    new_exp = refresh(future, factor=2.0, max_seconds=10000, now=NOW)
    remaining = (iso_to_dt(new_exp) - NOW).total_seconds()
    assert remaining == 200


def test_refresh_respects_max_cap():
    future = dt_to_iso(NOW + timedelta(seconds=10000))
    new_exp = refresh(future, factor=2.0, max_seconds=15000, now=NOW)
    remaining = (iso_to_dt(new_exp) - NOW).total_seconds()
    assert remaining == 15000


def test_refresh_does_not_revive_expired():
    past = dt_to_iso(NOW - timedelta(seconds=50))
    assert refresh(past, factor=2.0, max_seconds=1000, now=NOW) == past

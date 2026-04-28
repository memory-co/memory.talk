"""util.ttl — current_ttl(): seconds remaining; None → 0; expired → negative."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

from memorytalk.util.ttl import current_ttl, dt_to_iso


NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_current_ttl_null_is_zero():
    assert current_ttl(None, NOW) == 0


def test_current_ttl_positive_remaining():
    future = dt_to_iso(NOW + timedelta(seconds=100))
    assert current_ttl(future, NOW) == 100


def test_current_ttl_negative_when_expired():
    past = dt_to_iso(NOW - timedelta(seconds=50))
    assert current_ttl(past, NOW) == -50

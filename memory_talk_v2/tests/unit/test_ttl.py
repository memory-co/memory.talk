from datetime import datetime, timedelta, timezone

from memory_talk_v2.util.ttl import current_ttl, refresh, initial_expires_at, dt_to_iso, iso_to_dt


NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_current_ttl_null_is_zero():
    assert current_ttl(None, NOW) == 0


def test_current_ttl_positive_remaining():
    future = dt_to_iso(NOW + timedelta(seconds=100))
    assert current_ttl(future, NOW) == 100


def test_current_ttl_negative_when_expired():
    past = dt_to_iso(NOW - timedelta(seconds=50))
    assert current_ttl(past, NOW) == -50


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


def test_initial_expires_at_math():
    exp = initial_expires_at(3600, now=NOW)
    assert (iso_to_dt(exp) - NOW).total_seconds() == 3600

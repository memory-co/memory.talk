"""TTL utilities.

TTL is stored as an absolute `expires_at` ISO-8601 UTC timestamp, not a
countdown. Reads compute `ttl = expires_at - now`. NULL `expires_at` is the
default-link sentinel (always ttl=0, never refreshed).
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_to_dt(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def dt_to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def current_ttl(expires_at: str | None, now: datetime | None = None) -> int:
    """Seconds remaining. NULL → 0 (default-link sentinel)."""
    if expires_at is None:
        return 0
    now = now or now_utc()
    return int((iso_to_dt(expires_at) - now).total_seconds())


def refresh(
    expires_at: str,
    factor: float,
    max_seconds: int,
    now: datetime | None = None,
) -> str:
    """Compute new expires_at = now + min(remaining * factor, max).

    If already expired (remaining <= 0), do not refresh — returns the original.
    """
    now = now or now_utc()
    remaining = (iso_to_dt(expires_at) - now).total_seconds()
    if remaining <= 0:
        return expires_at
    new_remaining = min(remaining * factor, max_seconds)
    return dt_to_iso(now + timedelta(seconds=new_remaining))


def initial_expires_at(initial_seconds: int, now: datetime | None = None) -> str:
    now = now or now_utc()
    return dt_to_iso(now + timedelta(seconds=initial_seconds))

"""Timezone-aware instant parsing + canonical UTC-Z serialization.

Platform round timestamps arrive as heterogeneous strings (ms/sec
precision, ``Z`` or ``+08:00`` offsets), so they must be PARSED to aware
datetimes before any comparison — lexical string ordering is not
temporal ordering. Everything we store is re-serialized to second-
precision ``Z`` (matching the server's ``_utc_iso``).
"""
from __future__ import annotations

import datetime as _dt


def parse_instant(s: str | None) -> _dt.datetime | None:
    """Parse an ISO-8601 timestamp to an aware UTC-comparable datetime.
    Naive timestamps are assumed UTC. Returns None on empty/garbage."""
    if not s:
        return None
    try:
        dt = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=_dt.UTC)


def canonical_z(dt: _dt.datetime) -> str:
    """Serialize to second-precision UTC ``Z`` (the canonical form)."""
    return dt.astimezone(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def last_round_update_time(
    round_timestamps: list[str | None],
    *,
    created_at: str | None,
    synced_at: str | None,
) -> str:
    """A session's ``last_round_update_time``: the temporally latest
    parseable round timestamp, canonical UTC-Z. If no round has a
    parseable timestamp, fall back to ``created_at`` (conversation start),
    then ``synced_at`` (ingest moment)."""
    instants = [dt for ts in round_timestamps if (dt := parse_instant(ts))]
    if instants:
        return canonical_z(max(instants))
    floor = parse_instant(created_at) or parse_instant(synced_at)
    return canonical_z(floor) if floor else canonical_z(_dt.datetime.now(_dt.UTC))

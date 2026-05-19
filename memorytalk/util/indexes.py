"""indexes-string parsing shared by card and review writes.

Syntax (both inputs):
- range: ``"11-15"``      → [11, 12, 13, 14, 15]
- list:  ``"3,7,12"``     → [3, 7, 12]
- single: ``"4"``         → [4]

Rules:
- Values must be **strictly monotonically increasing** in the expanded list
  (forbids ``"15-11"`` and ``"12,7,3"``).
- Reject empty result.
"""
from __future__ import annotations


class IndexesParseError(ValueError):
    """Bad ``indexes`` string."""


def parse_indexes(indexes: str) -> list[int]:
    """Expand an ``indexes`` string into a strictly increasing list of ints."""
    if not indexes or not isinstance(indexes, str):
        raise IndexesParseError("indexes must be a non-empty string")

    out: list[int] = []
    for part in indexes.split(","):
        part = part.strip()
        if not part:
            raise IndexesParseError(f"empty segment in indexes: {indexes!r}")
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError as e:
                raise IndexesParseError(f"non-integer range: {part!r}") from e
            if lo > hi:
                raise IndexesParseError("indexes must be monotonically increasing")
            out.extend(range(lo, hi + 1))
        else:
            try:
                out.append(int(part))
            except ValueError as e:
                raise IndexesParseError(f"non-integer index: {part!r}") from e

    for a, b in zip(out, out[1:]):
        if a >= b:
            raise IndexesParseError("indexes must be monotonically increasing")
    return out

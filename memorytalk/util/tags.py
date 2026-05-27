"""User-side kv tag validation + CLI arg parsing.

Shared by:

  - HTTP layer (``PATCH /v3/sessions/{sid}/tags`` and ``PATCH
    /v3/cards/{cid}/tags`` — same constraints across object types)
  - CLI (``memory.talk session tag`` / ``memory.talk card tag``)
  - Repository (final write-time check before INSERT/UPDATE)

Why a single module:

  Tags are user-facing surface — the same key / value / count rules
  apply regardless of which object type carries them. Defining them in
  one place means there's exactly one place to add a new constraint
  (e.g. forbidden keys, value type widening) and exactly one error
  class for both API + CLI to catch.

Format rules (matches docs/cli/v3/session.md + card.md):

  key:    ^[a-zA-Z][a-zA-Z0-9_.-]*$   — leading letter, then word /
          dot / dash. Dot/dash reserved for namespacing (``ci.priority``)
          later.
  value:  string only, ≤ 200 chars.
  count:  ≤ 50 keys per object.

Errors are reported one at a time (first failure wins) — batch reports
would be nice but the API doesn't have a structured ``errors[]``
envelope; one clear message per call is enough.
"""
from __future__ import annotations

import re
from typing import Iterable


_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]*$")
MAX_VALUE_LEN = 200
MAX_TAGS_PER_OBJECT = 50


class TagValidationError(ValueError):
    """Raised on any tag constraint violation. The HTTP layer maps it to
    400; the CLI prints the message and exits 1."""


def validate_key(key: str) -> None:
    if not isinstance(key, str) or not _KEY_RE.match(key):
        raise TagValidationError(f"tag key '{key}' invalid")


def validate_value(key: str, value: object) -> None:
    if not isinstance(value, str):
        raise TagValidationError(
            f"tag value for '{key}' must be a string"
        )
    if len(value) > MAX_VALUE_LEN:
        raise TagValidationError(
            f"tag value for '{key}' too long (max {MAX_VALUE_LEN})"
        )


def validate_tag_dict(tags: dict) -> None:
    """Full validation against a final tag dict (post-merge for PATCH)."""
    if not isinstance(tags, dict):
        raise TagValidationError("tags must be an object")
    if len(tags) > MAX_TAGS_PER_OBJECT:
        raise TagValidationError(
            f"too many tags (max {MAX_TAGS_PER_OBJECT})"
        )
    for k, v in tags.items():
        validate_key(k)
        validate_value(k, v)


def apply_patch(current: dict, set_: dict, unset: Iterable[str]) -> dict:
    """Merge a PATCH onto ``current`` → return the new tag dict.

    Order: validate key shape in ``set_`` / ``unset`` first (caught
    early so server returns the most informative error), then enforce
    no-overlap (same key in both set and unset is operator confusion,
    not just bad data — must be rejected before we look at the merge),
    then materialize, then validate the result against value/count
    limits.
    """
    set_ = dict(set_ or {})
    unset_list = list(unset or [])

    overlap = set(set_) & set(unset_list)
    if overlap:
        # Pick a deterministic first key so the error message is stable
        # for tests.
        k = sorted(overlap)[0]
        raise TagValidationError(
            f"cannot both set and unset '{k}' in the same call"
        )

    # Key-shape pre-checks. ``set_`` value typing is also pre-checked so
    # we don't silently merge a non-string into ``current``.
    for k, v in set_.items():
        validate_key(k)
        validate_value(k, v)
    for k in unset_list:
        validate_key(k)

    out = dict(current or {})
    for k in unset_list:
        out.pop(k, None)
    out.update(set_)

    validate_tag_dict(out)  # post-merge count + final sanity
    return out


def parse_kv_args(args: Iterable[str]) -> tuple[dict, list[str]]:
    """CLI arg parser: split ``["k=v", "-k", "k2=v2"]`` into
    (``{k: v, k2: v2}``, ``["k"]``).

    Used by ``memory.talk session tag <sid> ...`` and
    ``memory.talk card tag <cid> ...``. The shape mirrors the HTTP
    PATCH body so the CLI can pass through without further translation.

    Rejects:
      - bare key without ``=`` and without leading ``-`` (ambiguous —
        could be a typo for either set-without-value or unset-without-
        dash, refuse instead of guessing)
      - empty value (`k=`): also ambiguous. If the user wants the empty
        string they can pass `k=""` via the shell; the parser here
        treats `k=` as malformed.
    """
    set_: dict[str, str] = {}
    unset: list[str] = []
    for raw in args:
        if not raw:
            continue
        if raw.startswith("-"):
            key = raw[1:]
            if not key:
                raise TagValidationError("empty unset key '-'")
            unset.append(key)
            continue
        if "=" not in raw:
            raise TagValidationError(
                f"'{raw}' is not K=V (set) or -K (unset)"
            )
        key, _, value = raw.partition("=")
        if not key:
            raise TagValidationError(f"empty key in '{raw}'")
        if value == "":
            raise TagValidationError(
                f"empty value in '{raw}' — use -{key} to unset"
            )
        set_[key] = value
    return set_, unset

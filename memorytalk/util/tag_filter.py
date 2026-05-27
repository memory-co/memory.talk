"""Tag filter parsing + SQL translation, shared between session and card lists.

Why this isn't part of ``util/dsl.py``:

  ``util/dsl.py`` is a tiny in-memory predicate evaluator for
  ``POST /v3/search``'s ``--where`` clause — it walks already-recalled
  candidate dicts in Python. Tag filtering on ``GET /v3/sessions``
  pushes down to SQLite directly (table can have 10k+ rows; can't
  afford an in-memory scan), so the *execution* is fundamentally
  different. The two only overlap on the operator alphabet, which is
  not enough to justify a shared abstraction with two backends — see
  the design discussion in the PR that introduced this file.

Why this isn't inlined in ``api/sessions.py``:

  Card list / card tag (next PR) will reuse exactly this shape. Both
  ``sessions.tags`` and ``cards.tags`` are JSON columns; the only
  difference is the SQL column name, which is parameterized.

5 operator forms (matches docs/cli/v3/session.md §--tag):

    K=V             eq         json_extract(<col>, '$.K') = ?
    K!=V            ne strict  json_extract(<col>, '$.K') != ?      (NULL excluded)
    K=V1,V2,V3      in         json_extract(<col>, '$.K') IN (?, ...)
    K               present    json_extract(<col>, '$.K') IS NOT NULL
    !K              absent     json_extract(<col>, '$.K') IS NULL
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from memorytalk.util.tags import TagValidationError, validate_key


TagOp = Literal["eq", "ne", "in", "present", "absent"]


@dataclass
class TagPredicate:
    """One ``--tag`` argument, parsed into structured form.

    ``values`` is a list because IN-form may carry multiple. eq / ne
    keep exactly one element; present / absent keep an empty list.
    Callers shouldn't poke at ``values`` directly — use ``to_sql`` to
    serialize.
    """
    key: str
    op: TagOp
    values: list[str]


def parse_tag_arg(arg: str) -> TagPredicate:
    """Parse one ``--tag`` argument string into a :class:`TagPredicate`.

    Empty / whitespace-only input → raises (don't silently swallow;
    the user almost certainly meant something).

    Order of checks matters:

      1. Leading ``!`` → ``!K`` absent (must check before ``!=`` because
         ``!K`` and ``K!=V`` both contain ``!``).
      2. ``!=`` substring → ``K!=V`` ne (must check before bare ``=``).
      3. ``=`` substring → eq / in (split RHS on ``,`` — N values → IN).
      4. Otherwise bare → ``K`` present.
    """
    if arg is None or not arg.strip():
        raise TagValidationError("empty tag filter")
    s = arg.strip()

    # 1. absent: '!K'
    if s.startswith("!"):
        key = s[1:]
        if not key:
            raise TagValidationError("empty key after '!'")
        validate_key(key)
        return TagPredicate(key=key, op="absent", values=[])

    # 2. strict ne: 'K!=V'
    if "!=" in s:
        key, _, value = s.partition("!=")
        if not key or value == "":
            raise TagValidationError(
                f"'{arg}' is not K!=V — missing key or value"
            )
        validate_key(key)
        return TagPredicate(key=key, op="ne", values=[value])

    # 3. eq or in: 'K=V' / 'K=V1,V2,V3'
    if "=" in s:
        key, _, value = s.partition("=")
        if not key or value == "":
            raise TagValidationError(
                f"'{arg}' is not K=V — missing key or value"
            )
        validate_key(key)
        # ``,`` splits into IN-list; single value stays eq. We don't
        # support escaping ``,`` in values — slug-shaped values are the
        # 95% case; documented limitation.
        values = value.split(",")
        if len(values) == 1:
            return TagPredicate(key=key, op="eq", values=values)
        # Reject empty parts: ``K=a,,b`` is almost certainly a typo,
        # not an intentional empty-string-in-set.
        if any(v == "" for v in values):
            raise TagValidationError(
                f"'{arg}' has an empty value in the IN-list"
            )
        return TagPredicate(key=key, op="in", values=values)

    # 4. present: 'K'
    validate_key(s)
    return TagPredicate(key=s, op="present", values=[])


def to_sql(
    predicates: list[TagPredicate], *, column: str = "tags",
) -> tuple[list[str], list]:
    """Translate a list of predicates to SQL fragments + bind params.

    Returns ``(clauses, params)`` — the caller AND-joins clauses into
    its WHERE. Per-clause params are appended into ``params`` in order.

    ``column`` is the SQL column name holding the tag JSON object —
    defaults to ``tags`` (sessions + cards both use that name). Param
    exists so future tables can plug in without touching this code.

    SQL injection note: the JSON path is interpolated as ``$.<key>``
    (no parameter binding for json paths in SQLite); ``<key>`` has
    already been through ``validate_key`` (matches ``^[a-zA-Z][a-zA-Z0-9_.-]*$``)
    so the only chars that can land in the path string are
    letters/digits/``._-``. No quote / no semicolon → no injection
    vector.
    """
    clauses: list[str] = []
    params: list = []
    for p in predicates:
        path = f"$.{p.key}"
        if p.op == "eq":
            clauses.append(f"json_extract({column}, ?) = ?")
            params.extend([path, p.values[0]])
        elif p.op == "ne":
            # Strict NE: NULL doesn't satisfy '!='. If users want
            # "either absent or not equal", they pass --tag !K too.
            clauses.append(f"json_extract({column}, ?) != ?")
            params.extend([path, p.values[0]])
        elif p.op == "in":
            placeholders = ", ".join(["?"] * len(p.values))
            clauses.append(f"json_extract({column}, ?) IN ({placeholders})")
            params.append(path)
            params.extend(p.values)
        elif p.op == "present":
            clauses.append(f"json_extract({column}, ?) IS NOT NULL")
            params.append(path)
        elif p.op == "absent":
            clauses.append(f"json_extract({column}, ?) IS NULL")
            params.append(path)
        else:
            # Should be unreachable; TagPredicate.op is Literal-typed.
            raise TagValidationError(f"unknown tag op: {p.op!r}")
    return clauses, params

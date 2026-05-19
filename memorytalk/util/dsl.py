"""Tiny `WHERE` DSL parser for ``POST /v3/search``.

Grammar (no precedence rules — left-to-right AND only):

    expr      := predicate ('AND' predicate)*
    predicate := field op value | field 'IN' list | field 'NOT' 'IN' list | field 'LIKE' string
    field     := identifier
    op        := '=' | '!=' | '<' | '>' | '<=' | '>='
    value     := string | number
    list      := '(' value (',' value)* ')'
    string    := '"' ... '"' | "'" ... "'"

Operators consciously omit ``OR`` — combining predicates by OR is rare for
the kinds of filters v3 needs (status / stats / metadata slicing), and
leaving it out keeps both grammar and execution model simple.

Field domains decide which candidate types a predicate applies to:

- ``type`` — universal, special-cased to filter the candidate stream
- card-only stats: ``review_up`` / ``review_down`` / ``review_neutral``
  / ``review_count`` / ``read_count`` / ``recall_count``,
  card metadata: ``card_id``
- session-only: ``session_id``, ``source``
- both: ``created_at``

If a predicate references a card-only field, *session* candidates fail
that predicate vacuously (and vice-versa). This makes
``review_count = 0`` auto-narrow to cards-only, ``source = "claude-code"``
auto-narrow to sessions-only — see docs/cli/v3/search.md "字段应用域规则".
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Callable


CARD_ONLY_FIELDS = {
    "card_id", "review_up", "review_down", "review_neutral",
    "review_count", "read_count", "recall_count",
}
SESSION_ONLY_FIELDS = {"session_id", "source"}
SHARED_FIELDS = {"created_at", "type"}

_ALL_FIELDS = CARD_ONLY_FIELDS | SESSION_ONLY_FIELDS | SHARED_FIELDS


class DSLError(ValueError):
    pass


@dataclass
class Predicate:
    field: str
    op: str            # =, !=, <, >, <=, >=, LIKE, IN, NOT_IN
    value: Any         # str / number / list

    def applies_to(self, kind: str) -> bool:
        """True if this predicate is meaningful for a `card` or `session` candidate."""
        if self.field in SHARED_FIELDS:
            return True
        if self.field in CARD_ONLY_FIELDS:
            return kind == "card"
        if self.field in SESSION_ONLY_FIELDS:
            return kind == "session"
        return True  # unknown — let evaluate decide

    def evaluate(self, candidate: dict, kind: str) -> bool:
        """Apply this predicate to a candidate dict. Fields not present
        in the candidate dict make the predicate fail (vacuously false)
        — that's how field-domain narrowing works."""
        if not self.applies_to(kind):
            return False  # vacuously fail: narrows to the other type
        # ``type`` is a synthetic field — read from kind, not the dict.
        if self.field == "type":
            return self._apply(kind)
        if self.field not in candidate:
            return False
        return self._apply(candidate[self.field])

    def _apply(self, v: Any) -> bool:
        op, rhs = self.op, self.value
        if op == "=":
            return _eq(v, rhs)
        if op == "!=":
            return not _eq(v, rhs)
        if op == "<":
            return _num(v) < _num(rhs)
        if op == ">":
            return _num(v) > _num(rhs)
        if op == "<=":
            return _num(v) <= _num(rhs)
        if op == ">=":
            return _num(v) >= _num(rhs)
        if op == "LIKE":
            return _like(str(v), str(rhs))
        if op == "IN":
            return any(_eq(v, x) for x in rhs)
        if op == "NOT_IN":
            return not any(_eq(v, x) for x in rhs)
        raise DSLError(f"unknown op: {op!r}")


@dataclass
class Filter:
    predicates: list[Predicate] = field(default_factory=list)

    def empty(self) -> bool:
        return not self.predicates

    def scope_includes(self, kind: str) -> bool:
        """True if at least one candidate of this kind could possibly pass.

        Used to decide whether to even bother running the LanceDB search
        for that bucket.
        """
        for p in self.predicates:
            if not p.applies_to(kind):
                return False
        return True

    def evaluate(self, candidate: dict, kind: str) -> bool:
        return all(p.evaluate(candidate, kind) for p in self.predicates)


# ────────── tokenizer + parser ──────────

_TOKEN_RE = re.compile(
    r"""\s*(?:
        (?P<str>"[^"]*"|'[^']*')                  # quoted string
        | (?P<num>-?\d+(?:\.\d+)?)                # number
        | (?P<op><=|>=|!=|=|<|>|\(|\)|,)          # operator / paren
        | (?P<word>[A-Za-z_][A-Za-z0-9_]*)        # identifier / keyword
    )""",
    re.VERBOSE,
)
_KEYWORDS = {"AND", "OR", "IN", "NOT", "LIKE"}


def _tokenize(s: str):
    pos = 0
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            raise DSLError(f"DSL parse error: unexpected character at offset {pos}: {s[pos:pos+10]!r}")
        pos = m.end()
        if m.group("str"):
            yield ("str", m.group("str")[1:-1])
        elif m.group("num"):
            yield ("num", float(m.group("num")) if "." in m.group("num") else int(m.group("num")))
        elif m.group("op"):
            yield ("op", m.group("op"))
        elif m.group("word"):
            w = m.group("word")
            if w.upper() in _KEYWORDS:
                yield ("kw", w.upper())
            else:
                yield ("ident", w)


def parse(expr: str) -> Filter:
    """Parse ``expr`` into a :class:`Filter`. Empty / None → empty filter."""
    if not expr or not expr.strip():
        return Filter()
    tokens = list(_tokenize(expr))
    if not tokens:
        return Filter()

    preds: list[Predicate] = []
    i = 0

    def peek():
        return tokens[i] if i < len(tokens) else (None, None)

    def consume():
        nonlocal i
        if i >= len(tokens):
            raise DSLError("DSL parse error: unexpected end of expression")
        tok = tokens[i]
        i += 1
        return tok

    def expect(kind, value=None):
        tok = consume()
        if tok[0] != kind or (value is not None and tok[1] != value):
            raise DSLError(f"DSL parse error: expected {kind!r}={value!r}, got {tok!r}")
        return tok

    while i < len(tokens):
        ident_tok = consume()
        if ident_tok[0] != "ident":
            raise DSLError(f"DSL parse error: expected field name, got {ident_tok!r}")
        field_name = ident_tok[1]
        if field_name not in _ALL_FIELDS:
            raise DSLError(f"DSL parse error: unknown field {field_name!r}")

        nxt = consume()
        if nxt[0] == "op" and nxt[1] in {"=", "!=", "<", ">", "<=", ">="}:
            rhs = consume()
            if rhs[0] not in ("str", "num"):
                raise DSLError(f"DSL parse error: expected value after {nxt[1]!r}, got {rhs!r}")
            preds.append(Predicate(field=field_name, op=nxt[1], value=rhs[1]))
        elif nxt[0] == "kw" and nxt[1] == "LIKE":
            rhs = consume()
            if rhs[0] != "str":
                raise DSLError("DSL parse error: LIKE requires a string pattern")
            preds.append(Predicate(field=field_name, op="LIKE", value=rhs[1]))
        elif nxt[0] == "kw" and nxt[1] == "IN":
            values = _parse_in_list(consume, expect)
            preds.append(Predicate(field=field_name, op="IN", value=values))
        elif nxt[0] == "kw" and nxt[1] == "NOT":
            expect("kw", "IN")
            values = _parse_in_list(consume, expect)
            preds.append(Predicate(field=field_name, op="NOT_IN", value=values))
        else:
            raise DSLError(f"DSL parse error: unexpected token after field {field_name!r}: {nxt!r}")

        # Connector
        if i < len(tokens):
            nxt = consume()
            if nxt[0] == "kw" and nxt[1] == "AND":
                continue
            raise DSLError(f"DSL parse error: expected 'AND' between predicates, got {nxt!r}")

    return Filter(predicates=preds)


def _parse_in_list(consume, expect):
    expect("op", "(")
    values: list[Any] = []
    while True:
        v = consume()
        if v[0] not in ("str", "num"):
            raise DSLError(f"DSL parse error: expected value in IN-list, got {v!r}")
        values.append(v[1])
        nxt = consume()
        if nxt == ("op", ")"):
            break
        if nxt != ("op", ","):
            raise DSLError(f"DSL parse error: expected ',' or ')' in IN-list, got {nxt!r}")
    if not values:
        raise DSLError("DSL parse error: IN-list cannot be empty")
    return values


# ────────── helpers ──────────

def _num(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError) as e:
        raise DSLError(f"non-numeric value: {x!r}") from e


def _eq(a: Any, b: Any) -> bool:
    # Permissive equality: try string compare first, then numeric. Allows
    # `tag = "x"` regardless of whether the stored value is a str or int.
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    try:
        return str(a) == str(b)
    except Exception:
        return False


def _like(value: str, pattern: str) -> bool:
    """SQL-LIKE: ``%`` matches any sequence (incl. empty), ``_`` matches one char.

    Case-insensitive. Built char-by-char rather than via ``re.escape`` +
    string-replace — Python's ``re.escape`` does NOT escape ``_`` or ``%``
    (neither is a regex metachar), so the naive replace can't reliably
    distinguish "this percent came from the pattern" from "this percent
    was already escaped". Walking the input is simpler and correct.
    """
    parts: list[str] = []
    for ch in pattern:
        if ch == "%":
            parts.append(".*")
        elif ch == "_":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    rx = "^" + "".join(parts) + "$"
    return re.match(rx, value, re.IGNORECASE) is not None

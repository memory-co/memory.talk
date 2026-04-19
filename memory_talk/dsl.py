"""Metadata filter DSL for `search` command.

Grammar (no OR, no parens, AND-only):

    expr       := predicate (AND? predicate)*
    predicate  := field op value
                | field (NOT)? LIKE string
                | field (NOT)? IN ( value_list )
    op         := = | != | > | >= | < | <=
    value      := string | reltime
    value_list := value (, value)*
    field      := session_id | card_id | tag | created_at
    string     := "..." (double-quoted, escape \\ and \")
    reltime    := -<N>(d|h|m|w)        (days/hours/minutes/weeks, relative to "now")

Fields:
    session_id    — both tables
    card_id       — cards ONLY; if present, sessions-side builder returns None
    tag           — multivalue (contains semantics via json_each)
    created_at    — both tables (each table's own column)

Compiled to SQLite parameterized WHERE fragments. `tag` expands to EXISTS
(SELECT 1 FROM json_each(<sessions_table>.tags) WHERE …).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Union


# ---------- AST ----------


@dataclass
class Predicate:
    field: str
    op: str           # one of: = != > >= < <= LIKE NOTLIKE IN NOTIN
    value: Union[str, list[str]]


# ---------- Fields & operators ----------

FIELDS = {"session_id", "card_id", "tag", "created_at"}
CARDS_ONLY_FIELDS = {"card_id"}
COMPARE_OPS = {"=", "!=", ">", ">=", "<", "<="}
KEYWORDS = {"AND", "LIKE", "NOT", "IN"}


class DSLError(ValueError):
    """Raised on any DSL syntax / semantic error."""


# ---------- Lexer ----------


@dataclass
class Token:
    kind: str         # IDENT KW STRING RELTIME OP LPAREN RPAREN COMMA
    value: str


_OP_CHARS = "=!<>"


def _tokenize(src: str) -> list[Token]:
    tokens: list[Token] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
            continue
        # string literal
        if c == '"':
            j = i + 1
            buf = []
            while j < n:
                cj = src[j]
                if cj == "\\" and j + 1 < n:
                    buf.append(src[j + 1])
                    j += 2
                    continue
                if cj == '"':
                    break
                buf.append(cj)
                j += 1
            if j >= n:
                raise DSLError("unterminated string literal")
            tokens.append(Token("STRING", "".join(buf)))
            i = j + 1
            continue
        # parens / comma
        if c == "(":
            tokens.append(Token("LPAREN", c))
            i += 1
            continue
        if c == ")":
            tokens.append(Token("RPAREN", c))
            i += 1
            continue
        if c == ",":
            tokens.append(Token("COMMA", c))
            i += 1
            continue
        # operators (= != > >= < <=)
        if c in _OP_CHARS:
            if c == "!" and i + 1 < n and src[i + 1] == "=":
                tokens.append(Token("OP", "!="))
                i += 2
                continue
            if c in "<>" and i + 1 < n and src[i + 1] == "=":
                tokens.append(Token("OP", c + "="))
                i += 2
                continue
            if c == "=":
                tokens.append(Token("OP", "="))
                i += 1
                continue
            if c in "<>":
                tokens.append(Token("OP", c))
                i += 1
                continue
            raise DSLError(f"unexpected character: {c}")
        # relative time: -<N><unit>
        if c == "-" and i + 1 < n and src[i + 1].isdigit():
            j = i + 1
            while j < n and src[j].isdigit():
                j += 1
            if j >= n or src[j] not in "dhmw":
                raise DSLError(f"malformed relative time near '{src[i:j+1]}'")
            tokens.append(Token("RELTIME", src[i:j + 1]))
            i = j + 1
            continue
        # identifier / keyword
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            upper = word.upper()
            tokens.append(Token("KW" if upper in KEYWORDS else "IDENT", upper if upper in KEYWORDS else word))
            i = j
            continue
        raise DSLError(f"unexpected character: {c!r}")
    return tokens


# ---------- Parser ----------


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self, offset: int = 0) -> Optional[Token]:
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def _consume(self, kind: str, value: Optional[str] = None) -> Token:
        tok = self._peek()
        if tok is None:
            raise DSLError(f"expected {value or kind}, got EOF")
        if tok.kind != kind or (value is not None and tok.value != value):
            raise DSLError(f"expected {value or kind}, got {tok.value!r}")
        self.pos += 1
        return tok

    def parse(self) -> list[Predicate]:
        if not self.tokens:
            return []
        preds = [self._predicate()]
        while self.pos < len(self.tokens):
            tok = self._peek()
            if tok and tok.kind == "KW" and tok.value == "AND":
                self.pos += 1
            preds.append(self._predicate())
        return preds

    def _predicate(self) -> Predicate:
        field_tok = self._consume("IDENT")
        field = field_tok.value
        if field not in FIELDS:
            raise DSLError(f"unknown field: {field!r}")

        nxt = self._peek()
        if nxt is None:
            raise DSLError(f"expected operator after {field!r}")

        # NOT LIKE / NOT IN
        if nxt.kind == "KW" and nxt.value == "NOT":
            self.pos += 1
            kw = self._consume("KW")
            if kw.value == "LIKE":
                return Predicate(field, "NOTLIKE", self._string())
            if kw.value == "IN":
                return Predicate(field, "NOTIN", self._value_list())
            raise DSLError(f"expected LIKE or IN after NOT, got {kw.value!r}")

        # LIKE / IN
        if nxt.kind == "KW":
            if nxt.value == "LIKE":
                self.pos += 1
                return Predicate(field, "LIKE", self._string())
            if nxt.value == "IN":
                self.pos += 1
                return Predicate(field, "IN", self._value_list())
            raise DSLError(f"unexpected keyword: {nxt.value!r}")

        # compare op
        if nxt.kind == "OP" and nxt.value in COMPARE_OPS:
            self.pos += 1
            return Predicate(field, nxt.value, self._value())

        raise DSLError(f"expected operator after {field!r}, got {nxt.value!r}")

    def _string(self) -> str:
        return self._consume("STRING").value

    def _value(self) -> str:
        tok = self._peek()
        if tok is None:
            raise DSLError("expected value, got EOF")
        if tok.kind == "STRING":
            self.pos += 1
            return tok.value
        if tok.kind == "RELTIME":
            self.pos += 1
            return tok.value  # kept as-is; compiler expands to ISO
        raise DSLError(f"expected string or relative time, got {tok.value!r}")

    def _value_list(self) -> list[str]:
        self._consume("LPAREN")
        out = [self._value()]
        while True:
            nxt = self._peek()
            if nxt and nxt.kind == "COMMA":
                self.pos += 1
                out.append(self._value())
            else:
                break
        self._consume("RPAREN")
        return out


def parse(expr: str) -> list[Predicate]:
    return _Parser(_tokenize(expr)).parse()


# ---------- Compiler ----------


_RELTIME_UNITS = {
    "d": "days",
    "h": "hours",
    "m": "minutes",
    "w": "weeks",
}


def _expand_reltime(token: str, now: datetime) -> str:
    # token like '-7d'; returns ISO string for the absolute instant
    unit = token[-1]
    amount = int(token[1:-1])
    delta = timedelta(**{_RELTIME_UNITS[unit]: amount})
    return (now - delta).isoformat()


def _resolve_value(val: str, now: datetime) -> str:
    if val.startswith("-") and len(val) >= 3 and val[-1] in _RELTIME_UNITS and val[1:-1].isdigit():
        return _expand_reltime(val, now)
    return val


_COMPARE_SQL = {
    "=": "=", "!=": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<=",
}


def _tag_fragment(sessions_alias: str, predicate: Predicate, params: list) -> str:
    """Build an EXISTS/NOT EXISTS fragment over sessions.tags (JSON list)."""
    op = predicate.op
    if op in ("=", "!=", ">", ">=", "<", "<=") or op == "LIKE":
        sql_op = _COMPARE_SQL.get(op, "LIKE")
        params.append(predicate.value)
        inner = f"value {sql_op} ?"
        if op == "!=":
            # "tag != x" means tags list does NOT contain x → NOT EXISTS equality
            return f"NOT EXISTS (SELECT 1 FROM json_each({sessions_alias}.tags) WHERE value = ?)"
        return f"EXISTS (SELECT 1 FROM json_each({sessions_alias}.tags) WHERE {inner})"
    if op == "NOTLIKE":
        params.append(predicate.value)
        return f"NOT EXISTS (SELECT 1 FROM json_each({sessions_alias}.tags) WHERE value LIKE ?)"
    if op == "IN":
        placeholders = ", ".join("?" for _ in predicate.value)
        params.extend(predicate.value)
        return f"EXISTS (SELECT 1 FROM json_each({sessions_alias}.tags) WHERE value IN ({placeholders}))"
    if op == "NOTIN":
        placeholders = ", ".join("?" for _ in predicate.value)
        params.extend(predicate.value)
        return f"NOT EXISTS (SELECT 1 FROM json_each({sessions_alias}.tags) WHERE value IN ({placeholders}))"
    raise DSLError(f"unsupported op for tag: {op}")


def _scalar_fragment(column: str, predicate: Predicate, params: list, now: datetime) -> str:
    op = predicate.op
    if op in COMPARE_OPS:
        params.append(_resolve_value(predicate.value, now))
        return f"{column} {_COMPARE_SQL[op]} ?"
    if op == "LIKE":
        params.append(predicate.value)
        return f"{column} LIKE ?"
    if op == "NOTLIKE":
        params.append(predicate.value)
        return f"{column} NOT LIKE ?"
    if op == "IN":
        resolved = [_resolve_value(v, now) for v in predicate.value]
        placeholders = ", ".join("?" for _ in resolved)
        params.extend(resolved)
        return f"{column} IN ({placeholders})"
    if op == "NOTIN":
        resolved = [_resolve_value(v, now) for v in predicate.value]
        placeholders = ", ".join("?" for _ in resolved)
        params.extend(resolved)
        return f"{column} NOT IN ({placeholders})"
    raise DSLError(f"unsupported op: {op}")


def build_cards_where(
    predicates: list[Predicate],
    now: Optional[datetime] = None,
) -> tuple[str, list]:
    """Compile predicates to a SQL fragment against `cards c LEFT JOIN sessions s`.

    Returns ('', []) when no predicates.
    """
    if not predicates:
        return "", []
    now = now or datetime.now()
    frags: list[str] = []
    params: list = []
    for p in predicates:
        if p.field == "card_id":
            frags.append(_scalar_fragment("c.card_id", p, params, now))
        elif p.field == "session_id":
            frags.append(_scalar_fragment("c.session_id", p, params, now))
        elif p.field == "created_at":
            frags.append(_scalar_fragment("c.created_at", p, params, now))
        elif p.field == "tag":
            frags.append(_tag_fragment("s", p, params))
        else:
            raise DSLError(f"unhandled field: {p.field}")
    return " AND ".join(frags), params


def build_sessions_where(
    predicates: list[Predicate],
    now: Optional[datetime] = None,
) -> Optional[tuple[str, list]]:
    """Compile predicates against `sessions s`.

    Returns `None` if any predicate references a cards-only field
    (e.g. `card_id`) — the sessions side cannot satisfy the filter, so
    the caller should skip sessions retrieval entirely.
    """
    if any(p.field in CARDS_ONLY_FIELDS for p in predicates):
        return None
    if not predicates:
        return "", []
    now = now or datetime.now()
    frags: list[str] = []
    params: list = []
    for p in predicates:
        if p.field == "session_id":
            frags.append(_scalar_fragment("s.session_id", p, params, now))
        elif p.field == "created_at":
            frags.append(_scalar_fragment("s.created_at", p, params, now))
        elif p.field == "tag":
            frags.append(_tag_fragment("s", p, params))
        else:
            raise DSLError(f"unhandled field: {p.field}")
    return " AND ".join(frags), params

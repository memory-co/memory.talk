"""Metadata filter DSL for /v2/search.

Grammar (AND-only, no OR, no parens):

    expr       := predicate (AND? predicate)*
    predicate  := field op value
                | field (NOT)? LIKE string
                | field (NOT)? IN ( value_list )
    op         := = | != | > | >= | < | <=
    value      := string | reltime
    value_list := value (, value)*
    field      := session_id | card_id | tag | source | created_at
    string     := "..." (double-quoted, escape \\ and \")
    reltime    := -<N>(d|h|m|w)      (days/hours/minutes/weeks, relative to now)

Fields:
    session_id    — both tables
    card_id       — cards ONLY (sessions-side builder returns None if present)
    tag           — multivalue (contains semantics via json_each)
    source        — sessions ONLY (v2 new; cards-side builder returns None if present)
    created_at    — both tables

Compiled to SQLite parameterized WHERE fragments. `tag` expands to
EXISTS (SELECT 1 FROM json_each(<table>.tags) WHERE ...).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Union


@dataclass
class Predicate:
    field: str
    op: str
    value: Union[str, list[str]]


FIELDS = {"session_id", "card_id", "tag", "source", "created_at"}
CARDS_ONLY_FIELDS = {"card_id"}
SESSIONS_ONLY_FIELDS = {"source"}
COMPARE_OPS = {"=", "!=", ">", ">=", "<", "<="}
KEYWORDS = {"AND", "LIKE", "NOT", "IN"}


class DSLError(ValueError):
    """Raised on any DSL syntax / semantic error."""


@dataclass
class Token:
    kind: str
    value: str


def _tokenize(src: str) -> list[Token]:
    i, n = 0, len(src)
    tokens: list[Token] = []
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf: list[str] = []
            while j < n:
                ch = src[j]
                if ch == "\\" and j + 1 < n:
                    nxt = src[j + 1]
                    if nxt == '"' or nxt == "\\":
                        buf.append(nxt)
                        j += 2
                        continue
                    buf.append(ch)
                    j += 1
                    continue
                if ch == '"':
                    tokens.append(Token("STRING", "".join(buf)))
                    i = j + 1
                    break
                buf.append(ch)
                j += 1
            else:
                raise DSLError("unterminated string")
            continue
        if c == "(":
            tokens.append(Token("LPAREN", "("))
            i += 1
            continue
        if c == ")":
            tokens.append(Token("RPAREN", ")"))
            i += 1
            continue
        if c == ",":
            tokens.append(Token("COMMA", ","))
            i += 1
            continue
        if c in "=!<>":
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
            raise DSLError(f"unexpected character {c!r}")
        if c == "-" and i + 1 < n and src[i + 1].isdigit():
            j = i + 1
            while j < n and src[j].isdigit():
                j += 1
            if j < n and src[j] in "dhmw":
                tokens.append(Token("RELTIME", src[i : j + 1]))
                i = j + 1
                continue
            raise DSLError(f"bad reltime starting at {src[i:]!r}")
        if c.isalpha() or c == "_":
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            kind = "KW" if word in KEYWORDS else "IDENT"
            tokens.append(Token(kind, word))
            i = j
            continue
        raise DSLError(f"unexpected character {c!r} at position {i}")
    return tokens


def _resolve_reltime(rt: str, now: datetime | None = None) -> str:
    unit = rt[-1]
    n = int(rt[1:-1])
    now = now or datetime.now(timezone.utc)
    if unit == "d":
        dt = now - timedelta(days=n)
    elif unit == "h":
        dt = now - timedelta(hours=n)
    elif unit == "m":
        dt = now - timedelta(minutes=n)
    elif unit == "w":
        dt = now - timedelta(weeks=n)
    else:
        raise DSLError(f"bad reltime unit: {unit}")
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse(src: str, now: datetime | None = None) -> list[Predicate]:
    """Parse DSL source into list[Predicate] (implicit AND between predicates)."""
    if not src or not src.strip():
        return []
    tokens = _tokenize(src)
    i = 0
    out: list[Predicate] = []

    def peek(offset: int = 0) -> Optional[Token]:
        return tokens[i + offset] if i + offset < len(tokens) else None

    while i < len(tokens):
        t = peek()
        if t is None:
            break
        if t.kind == "KW" and t.value == "AND":
            if not out:
                raise DSLError("leading AND")
            i += 1
            continue
        if t.kind != "IDENT":
            raise DSLError(f"expected field, got {t.kind} {t.value!r}")
        field = t.value
        if field not in FIELDS:
            raise DSLError(f"unknown field: {field}")
        i += 1

        nxt = peek()
        if nxt is None:
            raise DSLError(f"expected operator after {field}")

        if nxt.kind == "OP" and nxt.value in COMPARE_OPS:
            op = nxt.value
            i += 1
            v = peek()
            if v is None:
                raise DSLError(f"expected value after {op}")
            if v.kind == "STRING":
                out.append(Predicate(field, op, v.value))
            elif v.kind == "RELTIME":
                out.append(Predicate(field, op, _resolve_reltime(v.value, now)))
            else:
                raise DSLError(f"expected value, got {v.kind}")
            i += 1
            continue

        neg = False
        if nxt.kind == "KW" and nxt.value == "NOT":
            neg = True
            i += 1
            nxt = peek()
            if nxt is None:
                raise DSLError("dangling NOT")

        if nxt.kind == "KW" and nxt.value == "LIKE":
            i += 1
            v = peek()
            if v is None or v.kind != "STRING":
                raise DSLError("LIKE requires string")
            out.append(Predicate(field, "NOTLIKE" if neg else "LIKE", v.value))
            i += 1
            continue

        if nxt.kind == "KW" and nxt.value == "IN":
            i += 1
            lp = peek()
            if lp is None or lp.kind != "LPAREN":
                raise DSLError("IN requires (")
            i += 1
            vals: list[str] = []
            while True:
                v = peek()
                if v is None:
                    raise DSLError("unterminated IN list")
                if v.kind == "RPAREN":
                    i += 1
                    break
                if v.kind == "STRING":
                    vals.append(v.value)
                elif v.kind == "RELTIME":
                    vals.append(_resolve_reltime(v.value, now))
                else:
                    raise DSLError(f"unexpected {v.kind} in IN")
                i += 1
                sep = peek()
                if sep and sep.kind == "COMMA":
                    i += 1
                    continue
                if sep and sep.kind == "RPAREN":
                    i += 1
                    break
            out.append(Predicate(field, "NOTIN" if neg else "IN", vals))
            continue

        raise DSLError(f"unexpected token after {field}: {nxt.kind} {nxt.value!r}")

    return out


def compile_for(
    predicates: list[Predicate],
    table: str,
) -> Optional[tuple[str, list]]:
    """Compile predicates to (sql_fragment, params) for `table` in {'cards','sessions'}.

    Returns None if any predicate references a field that doesn't apply to this table
    (e.g. `card_id` on sessions, `source` on cards) — caller treats None as "this DSL
    can never match rows in this table".
    """
    if table not in ("cards", "sessions"):
        raise ValueError(f"unknown table: {table}")
    clauses: list[str] = []
    params: list = []
    for p in predicates:
        if table == "sessions" and p.field in CARDS_ONLY_FIELDS:
            return None
        if table == "cards" and p.field in SESSIONS_ONLY_FIELDS:
            return None
        if p.field == "tag":
            if p.op == "=":
                clauses.append(
                    f"EXISTS (SELECT 1 FROM json_each({table}.tags) WHERE value = ?)"
                )
                params.append(p.value)
            elif p.op == "!=":
                clauses.append(
                    f"NOT EXISTS (SELECT 1 FROM json_each({table}.tags) WHERE value = ?)"
                )
                params.append(p.value)
            elif p.op == "IN":
                placeholders = ",".join("?" * len(p.value))
                clauses.append(
                    f"EXISTS (SELECT 1 FROM json_each({table}.tags) WHERE value IN ({placeholders}))"
                )
                params.extend(p.value)
            elif p.op == "NOTIN":
                placeholders = ",".join("?" * len(p.value))
                clauses.append(
                    f"NOT EXISTS (SELECT 1 FROM json_each({table}.tags) WHERE value IN ({placeholders}))"
                )
                params.extend(p.value)
            else:
                raise DSLError(f"tag does not support operator {p.op}")
            continue
        col = p.field if p.field != "card_id" or table == "cards" else None
        if table == "cards" and p.field == "card_id":
            col = "card_id"
        if col is None:
            col = p.field
        if p.op in COMPARE_OPS:
            clauses.append(f"{table}.{col} {p.op} ?")
            params.append(p.value)
        elif p.op == "LIKE":
            clauses.append(f"{table}.{col} LIKE ?")
            params.append(p.value)
        elif p.op == "NOTLIKE":
            clauses.append(f"{table}.{col} NOT LIKE ?")
            params.append(p.value)
        elif p.op == "IN":
            placeholders = ",".join("?" * len(p.value))
            clauses.append(f"{table}.{col} IN ({placeholders})")
            params.extend(p.value)
        elif p.op == "NOTIN":
            placeholders = ",".join("?" * len(p.value))
            clauses.append(f"{table}.{col} NOT IN ({placeholders})")
            params.extend(p.value)
        else:
            raise DSLError(f"unknown operator {p.op}")
    if not clauses:
        return ("1=1", [])
    return (" AND ".join(clauses), params)

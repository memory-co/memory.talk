"""CLI: memory.talk card — the v4 question-graph surface.

A v4 card = one Issue (question) + several Positions (candidate answers)
competing by computed credence, connected by IBIS edges. Write commands:
``create`` / ``position`` / ``review`` / ``link``. Read commands (kept as
subcommands so the v3 top-level ``read``/``search``/``recall`` stay intact):
``read`` / ``search`` / ``recall``. All hit the ``/v4`` API.

Param style: every write flag is named (``--xx``); ``read``/``search`` take
a positional (bare id / query). Text flags (``--issue``/``--claim``/
``--scope``/``--comment``/``--prompt``) accept ``@<file>`` / ``@-`` (stdin)
so content with quotes/newlines bypasses shell+JSON escaping.
"""
from __future__ import annotations
import sys

import click

from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config

_STDIN_USED = []


def _read_text_arg(value: str | None) -> str | None:
    """Resolve a text flag: ``@<path>`` reads the file verbatim, ``@-``
    reads stdin (once per command), anything else is the literal value."""
    if value is None:
        return None
    if value == "@-":
        if _STDIN_USED:
            raise click.BadParameter("@- (stdin) can be used at most once")
        _STDIN_USED.append(True)
        return sys.stdin.read()
    if value.startswith("@"):
        with open(value[1:], encoding="utf-8") as f:
            return f.read()
    return value


def _parse_source(spec: str) -> tuple[str, str]:
    """``<session_id>:<indexes>`` → (session_id, indexes). indexes never
    contains a colon, so split on the last one."""
    if ":" not in spec:
        raise click.BadParameter(f"expected <session_id>:<indexes>, got {spec!r}")
    sid, indexes = spec.rsplit(":", 1)
    if not sid or not indexes:
        raise click.BadParameter(f"expected <session_id>:<indexes>, got {spec!r}")
    return sid, indexes


def _run(json_out: bool, method: str, path: str, body: dict | None,
         render, *, params=None):
    """Shared HTTP-call + emit + error-exit wrapper."""
    cfg = Config()
    try:
        result = api(method, path, cfg, json_body=body, params=params)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(f"error: {extract_error_message(e.payload)}")
        sys.exit(1)
    except Exception as e:
        emit_md_err(f"error: cannot reach server: {e}")
        sys.exit(1)
    if json_out:
        emit_json(result)
    else:
        emit_md(render(result))
    return result


@click.group("card")
def card() -> None:
    """v4 question graph: create / position / review / link / read / search / recall."""


# ────────── card create ──────────

@card.command("create")
@click.option("--issue", required=True, help="Question text (@file/@- ok)")
@click.option("--card_id", "card_id", default=None, help="Explicit card_<id>")
@click.option("--json", "json_out", is_flag=True, default=False)
def create(issue: str, card_id: str | None, json_out: bool) -> None:
    """Create a card (just an Issue; no answers)."""
    body = {"issue": _read_text_arg(issue)}
    if card_id:
        body["card_id"] = card_id
    _run(json_out, "POST", "/v4/cards", body, _fmt_create)


# ────────── card position ──────────

@card.command("position")
@click.option("--card", "card_ref", required=True, help="card_<id> to add an answer to")
@click.option("--claim", required=True, help="Answer text (@file/@- ok)")
@click.option("--source", "sources", multiple=True, help="<session_id>:<indexes>, repeatable")
@click.option("--scope", default=None, help="When this answer applies (@file/@- ok)")
@click.option("--position_id", "position_id", default=None)
@click.option("--json", "json_out", is_flag=True, default=False)
def position(card_ref, claim, sources, scope, position_id, json_out) -> None:
    """Add a candidate answer (Position) to an existing card."""
    body: dict = {"claim": _read_text_arg(claim)}
    if scope is not None:
        body["scope"] = _read_text_arg(scope)
    if position_id:
        body["position_id"] = position_id
    srcs = [_parse_source(s) for s in sources]
    if srcs:
        sid, idx = srcs[0]
        body["source"] = {"session_id": sid, "indexes": idx}
    result = _run(json_out, "POST", f"/v4/cards/{card_ref}/positions", body, _fmt_position)
    # extra provenance sessions beyond the first → POST .../sessions
    pid = result["position_id"]
    for sid, idx in srcs[1:]:
        cfg = Config()
        try:
            api("POST", f"/v4/cards/{card_ref}/sessions", cfg,
                json_body={"session_id": sid, "position_id": pid, "indexes": idx})
        except Exception:
            pass


# ────────── card review ──────────

@card.command("review")
@click.option("--position", "position_ref", required=True, help="pos_<id> to vote on")
@click.option("--argument", required=True, type=click.Choice(["+1", "1", "0", "-1"]),
              help="+1 pro / 0 neutral / -1 con")
@click.option("--cite", required=True, help="<session_id>:<indexes> evidence")
@click.option("--comment", default=None, help="One-line note (@file/@- ok)")
@click.option("--review_id", "review_id", default=None)
@click.option("--json", "json_out", is_flag=True, default=False)
def review(position_ref, argument, cite, comment, review_id, json_out) -> None:
    """Take a stance (argument ±1/0) on a Position."""
    sid, idx = _parse_source(cite)
    arg = int(argument.lstrip("+"))
    body: dict = {"position_id": position_ref, "session_id": sid,
                  "indexes": idx, "argument": arg}
    if comment is not None:
        body["comment"] = _read_text_arg(comment)
    if review_id:
        body["review_id"] = review_id
    _run(json_out, "POST", f"/v4/positions/{position_ref}/reviews", body, _fmt_review)


# ────────── card link ──────────

@card.command("link")
@click.option("--card", "card_ref", required=True)
@click.option("--type", "type_", required=True,
              type=click.Choice(["specializes", "suggested_by", "questions", "replaces", "related"]))
@click.option("--target", required=True, help="card_<id> (or pos_<id> for suggested_by)")
@click.option("--json", "json_out", is_flag=True, default=False)
def link(card_ref, type_, target, json_out) -> None:
    """Draw an IBIS edge between cards (card↔card / card→position)."""
    body = {"card_id": card_ref, "type": type_, "target_id": target}
    _run(json_out, "POST", f"/v4/cards/{card_ref}/links", body, _fmt_link)


# ────────── card read ──────────

@card.command("read")
@click.argument("id")
@click.option("--json", "json_out", is_flag=True, default=False)
def read(id: str, json_out: bool) -> None:
    """Read a card / position / session by id (prefix-dispatched)."""
    _run(json_out, "POST", "/v4/read", {"id": id}, _fmt_read)


# ────────── card search ──────────

@card.command("search")
@click.argument("query", default="")
@click.option("--where", "-w", default=None, help="DSL filter over the current answer")
@click.option("--limit", type=int, default=20, show_default=True)
@click.option("--json", "json_out", is_flag=True, default=False)
def search(query: str, where: str | None, limit: int, json_out: bool) -> None:
    """Find cards by issue/claim relevance (+ optional where DSL)."""
    body = {"query": query, "where": where, "limit": limit}
    _run(json_out, "POST", "/v4/search", body, _fmt_search)


# ────────── card recall ──────────

@card.command("recall")
@click.option("--session", "session_id", required=True)
@click.option("--prompt", required=True, help="Recall prompt (@file/@- ok)")
@click.option("--json", "json_out", is_flag=True, default=False)
def recall(session_id: str, prompt: str, json_out: bool) -> None:
    """Unconscious recall: collide on issue → inject current answer + scope."""
    body = {"session_id": session_id, "prompt": _read_text_arg(prompt)}
    _run(json_out, "POST", "/v4/recall", body, _fmt_recall)


# ────────── markdown formatters ──────────

def _fmt_create(r: dict) -> str:
    return f"✓ card created · `{r['card_id']}`"


def _fmt_position(r: dict) -> str:
    return f"✓ position added · `{r['position_id']}` on `{r['card_id']}`"


def _fmt_review(r: dict) -> str:
    return f"✓ review `{r['review_id']}` · argument {r['argument']:+d} on `{r['position_id']}`"


def _fmt_link(r: dict) -> str:
    return f"✓ link · `{r['card_id']}` --{r['type']}--> `{r['target_id']}` ({r['target_type']})"


def _pos_line(p: dict, *, current: bool) -> str:
    star = "★ " if current else "  "
    return (f"### {star}[POSITION] `{p['position_id']}` · "
            f"credence {p['credence']:+d} · ↑{p['up_count']} ↓{p['down_count']} ·{p['neutral_count']}\n"
            f"{p['claim']}"
            + (f"\n_scope: {p['scope']}_" if p.get('scope') else ""))


def _fmt_read(r: dict) -> str:
    t = r.get("type")
    if t == "card":
        c = r["card"]
        lines = [f"# card · `{c['card_id']}`", f"**Q:** {c['issue']}", ""]
        for i, p in enumerate(c["positions"]):
            lines.append(_pos_line(p, current=(i == 0)))
        if c.get("links"):
            lines.append("\n**links:**")
            for l in c["links"]:
                arrow = "→" if l["dir"] == "out" else "←"
                lines.append(f"- {arrow} {l['type']} `{l['target_id']}` ({l['target_type']})")
        if c.get("sessions"):
            lines.append("\n**sessions:** " + ", ".join(
                f"`{s['session_id']}`" for s in c["sessions"]))
        return "\n".join(lines)
    if t == "position":
        p = r["position"]
        lines = [f"# position · `{p['position_id']}`",
                 f"credence {p['credence']:+d} · ↑{p['up_count']} ↓{p['down_count']} ·{p['neutral_count']}",
                 p["claim"]]
        if p.get("scope"):
            lines.append(f"_scope: {p['scope']}_")
        lines.append(f"\n## reviews ({len(p.get('reviews', []))})")
        for rv in p.get("reviews", []):
            lines.append(f"- {rv['argument']:+d} `{rv['session_id']}` ({rv['indexes']})"
                         + (f" — {rv['comment']}" if rv.get("comment") else ""))
        return "\n".join(lines)
    if t == "session":
        return f"# session · `{r['session']['session_id']}` (v3 form)"
    return "（empty）"


def _fmt_search(r: dict) -> str:
    lines = [f"# search `{r['query']}` · {r['returned']}/{r['total']}"]
    for c in r["cards"]:
        top = c.get("top_position")
        n = c["position_count"]
        head = f"### [CARD] `{c['card_id']}` · {n} answer{'s' if n != 1 else ''}"
        if top:
            head += f" · credence {top['credence']:+d}"
        lines.append(head)
        lines.append(f"**Q:** {c['issue']}")
        lines.append(f"**A:** {top['claim']}" if top else "_(no answer yet)_")
    return "\n".join(lines)


def _fmt_recall(r: dict) -> str:
    cards = r["cards"]
    lines = [f"# recall · {len(cards)} card{'s' if len(cards) != 1 else ''}"]
    for c in cards:
        lines.append(f"### {c['issue']}")
        ans = c.get("answer")
        if ans:
            lines.append(ans["claim"])
            if ans.get("scope"):
                lines.append(f"_scope: {ans['scope']}_")
        else:
            lines.append("_(no answer yet)_")
        lines.append(f"`{c['card_id']}`")
    return "\n".join(lines)

"""CLI: memory.talk card — the v4 question-graph surface.

A v4 card = one Issue (question) + several Positions (candidate answers)
competing by computed credence, connected by IBIS edges. Write commands:
``create`` / ``position`` / ``review`` / ``link``. All hit the ``/v4`` API.

Reading a card is done through the top-level ``memory.talk read`` (it
prefix/fragment-dispatches card_/card_#p<n>/card_#l<n>/insight_/sess-);
search/recall are the
top-level ``memory.talk search`` / ``memory.talk recall``. Those commands
reuse the ``_fmt_read`` / ``_fmt_search`` / ``_fmt_recall`` formatters
defined at the bottom of this module.

Param style: every write flag is named (``--xx``). Text flags
(``--issue``/``--claim``/``--scope``/``--comment``) accept ``@<file>`` /
``@-`` (stdin) so content with quotes/newlines bypasses shell+JSON escaping.
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


# ────────── card list ──────────

def _fmt_list(r: dict) -> str:
    cards = r.get("cards", [])
    lines = [f"# cards ({r.get('returned', len(cards))}/{r.get('total', len(cards))})"]
    if not cards:
        lines.append("\n（none）")
        return "\n".join(lines)
    for c in cards:
        issue = " ".join((c.get("issue") or "").split())
        created = (c.get("created_at") or "")[:10]
        lines.append(
            f"- `{c.get('card_id', '')}` · "
            f"{c.get('position_count', 0)}p {c.get('link_count', 0)}l · "
            f"{created} — {issue}"
        )
    return "\n".join(lines)


@card.command("list")
@click.option("--since", default=None, help="ISO lower bound on created_at")
@click.option("--until", default=None, help="ISO upper bound on created_at")
@click.option("--limit", default=20, type=int, help="Max cards (1-200), newest first")
@click.option("--json", "json_out", is_flag=True, default=False)
def list_(since: str | None, until: str | None, limit: int, json_out: bool) -> None:
    """List cards, most recent first."""
    params: dict[str, str] = {"limit": str(limit)}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    _run(json_out, "GET", "/v4/cards", None, _fmt_list, params=params)


# ────────── card position ──────────

@card.command("position")
@click.option("--card", "card_ref", required=True, help="card_<id> to add an answer to")
@click.option("--claim", required=True, help="Answer text (@file/@- ok)")
@click.option("--source", "sources", multiple=True, help="<session_id>:<indexes>, repeatable")
@click.option("--scope", default=None, help="When this answer applies (@file/@- ok)")
@click.option("--forked_from", "forked_from", default=None,
              help="p<n> this answer is a refinement of")
@click.option("--json", "json_out", is_flag=True, default=False)
def position(card_ref, claim, sources, scope, forked_from, json_out) -> None:
    """Add a candidate answer (Position) to an existing card. Prints p<n>."""
    body: dict = {"claim": _read_text_arg(claim)}
    if scope is not None:
        body["scope"] = _read_text_arg(scope)
    if forked_from:
        body["forked_from"] = forked_from
    srcs = [_parse_source(s) for s in sources]
    if srcs:
        # Every --source rides in the position-create call; the service
        # lands one position_sessions row per source under the minted p<n>.
        body["sources"] = [{"session_id": sid, "indexes": idx} for sid, idx in srcs]
    _run(json_out, "POST", f"/v4/cards/{card_ref}/positions", body, _fmt_position)


# ────────── card review ──────────

@card.command("review")
@click.option("--target", "target", required=True,
              help="card_<id>#p<n> (position) or card_<id>#l<n> (link)")
@click.option("--argument", required=True, type=click.Choice(["+1", "1", "0", "-1"]),
              help="+1 pro / 0 neutral / -1 con")
@click.option("--cite", required=True, help="<session_id>:<indexes> evidence")
@click.option("--comment", default=None, help="One-line note (@file/@- ok)")
@click.option("--review_id", "review_id", default=None)
@click.option("--json", "json_out", is_flag=True, default=False)
def review(target, argument, cite, comment, review_id, json_out) -> None:
    """Take a stance (argument ±1/0) on a Position or a CardLink."""
    if "#" not in target:
        raise click.BadParameter("--target must be card_<id>#p<n> or card_<id>#l<n>")
    card_ref, _, seq = target.partition("#")
    kind = "links" if seq.startswith("l") else "positions"
    sid, idx = _parse_source(cite)
    arg = int(argument.lstrip("+"))
    body: dict = {"target": target, "session_id": sid,
                  "indexes": idx, "argument": arg}
    if comment is not None:
        body["comment"] = _read_text_arg(comment)
    if review_id:
        body["review_id"] = review_id
    _run(json_out, "POST", f"/v4/cards/{card_ref}/{kind}/{seq}/reviews",
         body, _fmt_review)


# ────────── card link ──────────

@card.command("link")
@click.option("--card", "card_ref", required=True)
@click.option("--type", "type_", required=True,
              type=click.Choice(["specializes", "suggested_by", "questions", "replaces", "related"]))
@click.option("--target", required=True, help="card_<id> (or card_<id>#p<n> for suggested_by)")
@click.option("--claim", required=True, help="Why this edge holds (@file/@- ok)")
@click.option("--source", "sources", multiple=True, help="<session_id>:<indexes>, repeatable")
@click.option("--json", "json_out", is_flag=True, default=False)
def link(card_ref, type_, target, claim, sources, json_out) -> None:
    """Draw a governed IBIS edge between cards (card↔card / card→position).
    Prints l<n>; the edge is itself reviewable. Each --source lands one
    link_sessions provenance row under the minted l<n>."""
    body = {"card_id": card_ref, "type": type_, "target_id": target,
            "claim": _read_text_arg(claim)}
    srcs = [_parse_source(s) for s in sources]
    if srcs:
        body["source"] = [{"session_id": sid, "indexes": idx} for sid, idx in srcs]
    _run(json_out, "POST", f"/v4/cards/{card_ref}/links", body, _fmt_link)


# ────────── markdown formatters ──────────
#
# read / search / recall are NOT card subcommands — they are the top-level
# ``memory.talk {read,search,recall}`` commands (cli/read.py, cli/search.py,
# cli/recall.py), which import the formatters below.

def _fmt_create(r: dict) -> str:
    return f"✓ card created · `{r['card_id']}`"


def _fmt_position(r: dict) -> str:
    return f"✓ position added · `{r['position']}` on `{r['card_id']}` (`{r['card_id']}#{r['position']}`)"


def _fmt_review(r: dict) -> str:
    return (f"✓ review `{r['review_id']}` · argument {r['argument']:+d} on "
            f"`{r['target']}` ({r['target_kind']})")


def _fmt_link(r: dict) -> str:
    return (f"✓ link `{r['link']}` · `{r['card_id']}` --{r['type']}--> "
            f"`{r['target_id']}` ({r['target_type']})")


def _pos_line(p: dict, *, current: bool) -> str:
    star = "★ " if current else "  "
    addr = p.get("id") or f"{p.get('card_id', '')}#{p.get('position', '')}"
    return (f"### {star}[POSITION] `{addr}` · "
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
                cred = f" · credence {l['credence']:+d}" if "credence" in l else ""
                claim = f" — {l['claim']}" if l.get("claim") else ""
                lines.append(
                    f"- {arrow} {l['type']} `{l['target_id']}` "
                    f"({l['target_type']}){cred}{claim}")
        if c.get("sessions"):
            lines.append("\n**sessions:** " + ", ".join(
                f"`{s['session_id']}`" for s in c["sessions"]))
        return "\n".join(lines)
    if t == "position":
        p = r["position"]
        addr = p.get("id") or f"{p.get('card_id', '')}#{p.get('position', '')}"
        lines = [f"# position · `{addr}`",
                 f"credence {p['credence']:+d} · ↑{p['up_count']} ↓{p['down_count']} ·{p['neutral_count']}",
                 p["claim"]]
        if p.get("scope"):
            lines.append(f"_scope: {p['scope']}_")
        lines.append(f"\n## reviews ({len(p.get('reviews', []))})")
        for rv in p.get("reviews", []):
            lines.append(f"- {rv['argument']:+d} `{rv['session_id']}` ({rv['indexes']})"
                         + (f" — {rv['comment']}" if rv.get("comment") else ""))
        return "\n".join(lines)
    if t == "link":
        l = r["link"]
        addr = l.get("id") or f"{l.get('card_id', '')}#{l.get('link', '')}"
        lines = [f"# link · `{addr}` ({l['type']} → `{l['target_id']}`)",
                 f"credence {l['credence']:+d} · ↑{l['up_count']} ↓{l['down_count']} ·{l['neutral_count']}"]
        if l.get("claim"):
            lines.append(l["claim"])
        lines.append(f"\n## reviews ({len(l.get('reviews', []))})")
        for rv in l.get("reviews", []):
            lines.append(f"- {rv['argument']:+d} `{rv['session_id']}` ({rv['indexes']})"
                         + (f" — {rv['comment']}" if rv.get("comment") else ""))
        return "\n".join(lines)
    if t == "insight":
        c = r["insight"]
        iid = c.get("insight_id") or c.get("card_id")
        lines = [f"# insight · `{iid}` (read-only)", c.get("insight", "")]
        st = c.get("stats") or {}
        if st:
            lines.append(
                f"_reads {st.get('read_count', 0)} · recalls "
                f"{st.get('recall_count', 0)}_"
            )
        return "\n".join(lines)
    if t == "mark":
        return _fmt_read_mark(r)
    if t == "session":
        return _fmt_read_session(r["session"])
    return "（empty）"


def _issue_line(iss: dict) -> str:
    """One resolved ``#…？`` issue: its text + whether it created a new card
    or linked an existing one. Mirrors the submit-result rendering."""
    tag = "new card" if iss.get("is_new") else "linked"
    idx = f" ({iss['indexes']})" if iss.get("indexes") else ""
    return f"  - #{iss.get('issue', '')}？{idx} → {tag} `{iss.get('card_id', '')}`"


def _fmt_read_mark(r: dict) -> str:
    """``read sess_…#m<n>`` — one mark's full body: scenario (description),
    last_index, and each walked round (comment + resolved issues→cards).
    ``r`` is the read envelope ``{id, session_id, mark_seq, mark: <body>}``."""
    body = r.get("mark") or {}
    addr = r.get("id")
    if not addr:
        sid, seq = r.get("session_id", ""), r.get("mark_seq", "")
        addr = f"{sid}#{seq}" if sid and seq else (seq or sid)
    lines = [f"# mark · `{addr}`" if addr else "# mark"]
    if body.get("description"):
        lines.append(f"_scenario: {body['description']}_")
    if body.get("last_index") is not None:
        lines.append(f"_last_index: {body['last_index']}_")
    rounds = body.get("rounds") or []
    lines.append(f"\n## rounds ({len(rounds)})")
    for rd in rounds:
        head = f"### [#{rd.get('index')}]"
        lines.append(head)
        if rd.get("comment"):
            lines.append(str(rd["comment"]))
        for iss in rd.get("issues") or []:
            lines.append(_issue_line(iss))
    return "\n".join(lines)


# Single round's text is capped so one giant turn doesn't blow up the
# rendered session; the full content is always available via `--json`.
_ROUND_TEXT_CAP = 2000


def _flatten_round_text(blocks: list) -> str:
    """Project a round's content blocks to displayable text. Text /
    thinking blocks render verbatim; other block types (tool_use,
    tool_result, …) show a ``_(type)_`` placeholder so the round isn't
    silently empty."""
    out: list[str] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        txt = b.get("text") or b.get("thinking")
        if txt:
            out.append(str(txt))
            continue
        out.append(f"_({b.get('type') or 'block'})_")
    return "\n\n".join(out)


def _fmt_read_session(s: dict) -> str:
    lines = [f"# session · `{s['session_id']}`"]
    meta_bits = []
    if s.get("source"):
        meta_bits.append(f"source `{s['source']}`")
    rounds = s.get("rounds") or []
    meta_bits.append(f"{len(rounds)} round{'s' if len(rounds) != 1 else ''}")
    if s.get("created_at"):
        meta_bits.append(f"created {s['created_at']}")
    lines.append(" · ".join(meta_bits))
    lines.append("")
    for i, rd in enumerate(rounds):
        speaker = rd.get("speaker") or rd.get("role") or ""
        head = f"### [#{rd.get('index', i)}]"
        if speaker:
            head += f" {speaker}"
        lines.append(head)
        text = _flatten_round_text(rd.get("content"))
        if len(text) > _ROUND_TEXT_CAP:
            text = text[:_ROUND_TEXT_CAP] + " …"
        lines.append(text)
    marks = s.get("marks") or []
    if marks:
        lines.append(f"\n## marks ({len(marks)})")
        for mk in marks:
            # Concise line per mark — full single-mark detail is `read sess#m<n>`.
            mk_rounds = mk.get("rounds") or []
            issues = [iss for rd in mk_rounds for iss in (rd.get("issues") or [])]
            cov = f"{len(mk_rounds)} round{'s' if len(mk_rounds) != 1 else ''}"
            if issues:
                cards = " · ".join(
                    f"#{i.get('issue', '')}？→{'new' if i.get('is_new') else 'linked'} "
                    f"`{i.get('card_id', '')}`"
                    for i in issues
                )
            else:
                cards = "_(no issues)_"
            lines.append(f"- `{mk['mark']}` · {cov} · {cards}")
    return "\n".join(lines)


def _fmt_search(r: dict) -> str:
    """Unified search render: a mixed relevance-ranked stream of card /
    insight / session hits (each item tagged with ``kind``)."""
    lines = [f"# search `{r['query']}` · {r['returned']}/{r['total']}"]
    for c in r["cards"]:
        kind = c.get("kind", "card")
        if kind == "insight":
            lines.append(f"### [INSIGHT] `{c.get('insight_id', '')}`")
            lines.append(c.get("insight", ""))
        elif kind == "session":
            n = c.get("hit_count", 0)
            lines.append(
                f"### [SESSION] `{c['session_id']}` · {n} hit{'s' if n != 1 else ''}"
                f" · {c.get('source', '')}")
            for h in c.get("hits", []):
                lines.append(f"- _[#{h['index']} {h.get('role', '')}]_ {h.get('text', '')}")
        else:
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
    cards = r.get("cards") or []
    # No matches → empty string so the hook injects no context.
    if not cards:
        return ""
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

"""Markdown formatters for v2 CLI.

Each function takes a response dict (typically straight from the API) and
returns a Markdown string. The shapes are pinned to ``docs/cli/v2/<cmd>.md``
— update those docs in lockstep when changing what's emitted here.

Direction labels (`TO` / `FROM`) on link lines are intentionally not
emitted yet — see the TODO(code) callouts in `docs/cli/v2/search.md` and
`view.md`.
"""
from __future__ import annotations
from typing import Any


# ---------- helpers ----------

def _join(*lines: str) -> str:
    """Join lines with '\n', collapse 3+ blanks to 2, ensure trailing newline."""
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _link_line(link: dict) -> str:
    """`<peer_id>` (type[ · expired]) [· comment]"""
    peer = link.get("target_id", "")
    ptype = link.get("target_type", "")
    ttl = link.get("ttl")
    comment = link.get("comment")

    type_inner = ptype
    if isinstance(ttl, (int, float)) and ttl < 0:
        type_inner = f"{ptype} · expired"

    parts = [f"`{peer}` ({type_inner})"]
    if comment:
        parts.append(comment)
    return " · ".join(parts)


def _links_section(links: list[dict], max_show: int = 3) -> list[str]:
    if not links:
        return []
    out = ["**Links:**", ""]
    for link in links[:max_show]:
        out.append(f"- {_link_line(link)}")
    if len(links) > max_show:
        out.append(f"- +{len(links) - max_show} more")
    out.append("")
    return out


# ---------- error ----------

def fmt_error(message: str) -> str:
    return f"**error:** {message}\n"


# ---------- search ----------

def fmt_search(resp: dict) -> str:
    out: list[str] = []
    query = resp.get("query") or "*(empty)*"
    out.append(f"# search: {query}")
    out.append("")
    out.append(f"`search_id={resp.get('search_id', '')}`")
    out.append("")

    cards = resp.get("cards") or {"count": 0, "results": []}
    out.append(f"## cards ({cards.get('count', 0)})")
    out.append("")
    for r in cards.get("results") or []:
        out.append(f"### {r['rank']}. CARD `{r['card_id']}`")
        out.append("")
        if r.get("summary"):
            out.append(f"**Summary:** {r['summary']}")
            out.append("")
        snippets = r.get("snippets") or []
        if snippets:
            out.append("**Snippets:**")
            out.append("")
            for s in snippets:
                out.append(f"- {s}")
            out.append("")
        out.extend(_links_section(r.get("links") or []))

    sessions = resp.get("sessions") or {"count": 0, "results": []}
    out.append(f"## sessions ({sessions.get('count', 0)})")
    out.append("")
    for r in sessions.get("results") or []:
        out.append(f"### {r['rank']}. SESSION `{r['session_id']}`")
        out.append("")
        tags = r.get("tags") or []
        if tags:
            out.append("**Tags:** " + ", ".join(f"`{t}`" for t in tags))
            out.append("")
        snippets = r.get("snippets") or []
        if snippets:
            out.append("**Snippets:**")
            out.append("")
            for s in snippets:
                out.append(f"- {s}")
            out.append("")
        out.extend(_links_section(r.get("links") or []))
        if r.get("source"):
            out.append(f"**Source:** {r['source']}")
            out.append("")

    return _join(*out)


# ---------- view ----------

def fmt_view_card(resp: dict) -> str:
    card = resp.get("card") or {}
    out: list[str] = []
    out.append(f"# CARD `{card.get('card_id', '')}`")
    out.append("")
    if card.get("summary"):
        out.append(f"**Summary:** {card['summary']}")
        out.append("")

    rounds = card.get("rounds") or []
    out.append(f"## rounds ({len(rounds)})")
    out.append("")
    for i, r in enumerate(rounds, start=1):
        sid = r.get("session_id", "")
        idx = r.get("index", "")
        role = r.get("role") or ""
        text = r.get("text") or ""
        out.append(f"{i}. **[`{sid}`#{idx} {role}]** {text}")
    out.append("")

    links = resp.get("links") or []
    out.append(f"## links ({len(links)})")
    out.append("")
    for link in links:
        out.append(f"- {_link_line(link)}")
    out.append("")

    return _join(*out)


def fmt_view_session(resp: dict) -> str:
    sess = resp.get("session") or {}
    out: list[str] = []
    out.append(f"# SESSION `{sess.get('session_id', '')}`")
    out.append("")
    if sess.get("created_at"):
        out.append(f"**Created:** `{sess['created_at']}`")
        out.append("")
    tags = sess.get("tags") or []
    if tags:
        out.append("**Tags:** " + ", ".join(f"`{t}`" for t in tags))
        out.append("")
    metadata = sess.get("metadata") or {}
    if metadata:
        out.append("**Metadata:**")
        out.append("")
        for k, v in metadata.items():
            out.append(f"- {k}: `{v}`")
        out.append("")

    rounds = sess.get("rounds") or []
    out.append(f"## rounds ({len(rounds)})")
    out.append("")
    for r in rounds:
        idx = r.get("index", "")
        role = r.get("role") or ""
        text = "".join(b.get("text") or "" for b in (r.get("content") or []) if b.get("type") in ("text", "code"))
        extras = sorted({b.get("type") for b in (r.get("content") or []) if b.get("type") not in ("text", "code")})
        extras_tag = "".join(f" +{e}" for e in extras if e)
        out.append(f"{r.get('index') or idx}. **[#{idx} {role}{extras_tag}]** {text}")
    out.append("")

    links = resp.get("links") or []
    out.append(f"## links ({len(links)})")
    out.append("")
    for link in links:
        out.append(f"- {_link_line(link)}")
    out.append("")

    if sess.get("source"):
        out.append("---")
        out.append("")
        out.append(f"**Source:** {sess['source']}")
        out.append("")

    return _join(*out)


def fmt_view(resp: dict) -> str:
    if resp.get("type") == "card":
        return fmt_view_card(resp)
    if resp.get("type") == "session":
        return fmt_view_session(resp)
    return fmt_error(f"unknown view type: {resp.get('type')!r}")


# ---------- log ----------

def _detail_summary(kind: str, detail: dict) -> str:
    if kind == "imported":
        return f"source={detail.get('source', '')} · round_count={detail.get('round_count', '')}"
    if kind == "rounds_appended":
        return (
            f"indexes {detail.get('from_index', '?')}-{detail.get('to_index', '?')} "
            f"(+{detail.get('added_count', '?')})"
        )
    if kind == "rounds_overwrite_skipped":
        idxs = detail.get("indexes", [])
        return f"indexes={','.join(str(i) for i in idxs)}"
    if kind == "tag_added" or kind == "tag_removed":
        return f"`{detail.get('tag', '')}`"
    if kind == "card_extracted":
        return f"`{detail.get('card_id', '')}` · indexes={detail.get('indexes', '')}"
    if kind == "linked":
        direction = detail.get("direction") or ""
        peer = detail.get("peer_id") or ""
        comment = detail.get("comment") or ""
        arrow = "←incoming" if direction == "incoming" else "→outgoing"
        parts = [f"{arrow} `{peer}`"]
        if comment:
            parts.append(f"({comment})")
        return " ".join(parts)
    if kind == "created":
        summary = detail.get("summary") or ""
        rounds = detail.get("rounds") or []
        rounds_part = ", ".join(f"`{r['session_id']}`/{r['indexes']}" for r in rounds) or "(none)"
        n_default = len(detail.get("default_links") or [])
        from_search = detail.get("from_search_id")
        bits = [summary, f"rounds={rounds_part}", f"{n_default} default_link" + ("s" if n_default != 1 else "")]
        if from_search:
            bits.append(f"from `{from_search}`")
        return " · ".join(bits)
    # Fallback: compact key=val
    if isinstance(detail, dict) and detail:
        return " · ".join(f"{k}={v}" for k, v in detail.items())
    return ""


def _fmt_log_table(events: list[dict]) -> list[str]:
    out = [
        "| at | kind | detail |",
        "|---|---|---|",
    ]
    for e in events:
        at = e.get("at", "")
        kind = e.get("kind", "")
        detail = _detail_summary(kind, e.get("detail") or {})
        # Escape pipes inside detail to keep table valid.
        detail = detail.replace("|", "\\|")
        out.append(f"| `{at}` | {kind} | {detail} |")
    return out


def fmt_log_card(resp: dict) -> str:
    events = resp.get("events") or []
    out = [
        f"# CARD `{resp.get('card_id', '')}` · {len(events)} events",
        "",
    ]
    out.extend(_fmt_log_table(events))
    out.append("")
    return _join(*out)


def fmt_log_session(resp: dict) -> str:
    events = resp.get("events") or []
    out = [
        f"# SESSION `{resp.get('session_id', '')}` · {len(events)} events",
        "",
    ]
    out.extend(_fmt_log_table(events))
    out.append("")
    return _join(*out)


def fmt_log(resp: dict) -> str:
    if resp.get("type") == "card":
        return fmt_log_card(resp)
    if resp.get("type") == "session":
        return fmt_log_session(resp)
    return fmt_error(f"unknown log type: {resp.get('type')!r}")


# ---------- write commands (single line ok) ----------

def fmt_card_create(resp: dict) -> str:
    return f"ok: created `{resp.get('card_id', '')}`\n"


def fmt_link_create(resp: dict) -> str:
    return f"ok: linked `{resp.get('link_id', '')}`\n"


def fmt_tag(resp: dict) -> str:
    tags = resp.get("tags") or []
    if not tags:
        return "ok: tags = *(empty)*\n"
    return "ok: tags = " + ", ".join(f"`{t}`" for t in tags) + "\n"


# ---------- sync / rebuild ----------

def fmt_sync(resp: dict) -> str:
    out = [
        f"# sync · **{resp.get('status', 'ok')}**",
        "",
        "| field | count |",
        "|---|---|",
    ]
    for key in ("discovered", "imported", "skipped", "appended", "overwrite_warnings", "errors"):
        if key in resp:
            out.append(f"| {key} | {resp[key]} |")
    out.append("")
    return _join(*out)


def fmt_rebuild(resp: dict) -> str:
    out = [
        f"# rebuild · **{resp.get('status', 'ok')}**",
        "",
        "| field | count |",
        "|---|---|",
    ]
    for key, label in (
        ("sessions", "sessions"),
        ("cards", "cards"),
        ("searches_replayed", "searches_replayed"),
        ("events_replayed", "events_replayed"),
        ("errors_count", "errors"),
    ):
        if key in resp:
            out.append(f"| {label} | {resp[key]} |")
    out.append("")
    return _join(*out)


# ---------- server ----------

def fmt_server_start(payload: dict) -> str:
    status = payload.get("status", "")
    if status == "started":
        return f"**started** · pid `{payload.get('pid', '')}` · port `{payload.get('port', '')}`\n"
    if status == "already_running":
        return f"**already_running** · pid `{payload.get('pid', '')}` · port `{payload.get('port', '')}`\n"
    if status == "failed":
        # Render as an error block; caller handles exit code.
        err = payload.get("error", "")
        ec = payload.get("exit_code", "")
        return _join(
            f"**error:** server failed to start (exit_code={ec})",
            "",
            "```",
            err,
            "```",
        )
    return f"{status}\n"


def fmt_server_stop(payload: dict) -> str:
    status = payload.get("status", "")
    if status == "stopped":
        return f"**stopped** · pid `{payload.get('pid', '')}`\n"
    if status == "not_running":
        return "**not_running**\n"
    return f"{status}\n"


def fmt_status(payload: dict) -> str:
    status = payload.get("status", "")
    if status == "running":
        out = [
            f"# memory-talk · **running**",
            "",
            "| field | value |",
            "|---|---|",
            f"| data_root | `{payload.get('data_root', '')}` |",
            f"| settings | `{payload.get('settings_path', '')}` |",
            f"| sessions | {payload.get('sessions_total', 0)} |",
            f"| cards | {payload.get('cards_total', 0)} |",
            f"| links | {payload.get('links_total', 0)} |",
            f"| searches | {payload.get('searches_total', 0)} |",
            f"| embedding | {payload.get('embedding_provider', '')} |",
            f"| vector | {payload.get('vector_provider', '')} |",
            f"| relation | {payload.get('relation_provider', '')} |",
            "",
        ]
        return _join(*out)
    out = [
        f"# memory-talk · **{status or 'unknown'}**",
        "",
        f"- data_root: `{payload.get('data_root', '')}`",
        f"- settings: `{payload.get('settings_path', '')}`",
        "",
    ]
    return _join(*out)

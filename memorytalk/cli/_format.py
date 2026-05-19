"""Markdown formatters — one ``fmt_<cmd>`` per command output shape.

Each formatter takes the parsed JSON payload and returns Markdown text
that ``_render.emit_md()`` ships to stdout. The Markdown matches the
contract in docs/cli/v3/<cmd>.md exactly — adjust the contract first,
then the formatter.
"""
from __future__ import annotations
from typing import Any


# ────────── generic ──────────

def fmt_error(msg: str) -> str:
    return f"**error:** {msg}\n"


# ────────── server ──────────

def fmt_server_start(payload: dict) -> str:
    status = payload.get("status", "")
    if status == "started":
        return f"**started** · pid `{payload['pid']}` · port `{payload['port']}`\n"
    if status == "already_running":
        return f"**already_running** · pid `{payload['pid']}` · port `{payload['port']}`\n"
    if status == "failed":
        err = payload.get("error", "").strip()
        body = f"**error:** server failed to start (exit_code={payload.get('exit_code')})\n"
        if err:
            body += f"\n```\n{err}\n```\n"
        return body
    return f"**{status}**\n"


def fmt_server_stop(payload: dict) -> str:
    status = payload.get("status", "")
    if status == "stopped":
        return f"**stopped** · pid `{payload['pid']}`\n"
    if status == "not_running":
        return "**not_running**\n"
    return f"**{status}**\n"


def fmt_status(payload: dict) -> str:
    if payload.get("status") == "not_running":
        return (
            "# memory-talk · **not_running**\n\n"
            f"- data_root: `{payload.get('data_root', '')}`\n"
            f"- settings: `{payload.get('settings_path', '')}`\n"
        )
    lines = [
        "# memory-talk · **running**",
        "",
        "| field | value |",
        "|---|---|",
        f"| data_root | `{payload['data_root']}` |",
        f"| settings | `{payload['settings_path']}` |",
        f"| sessions | {payload['sessions_total']} |",
        f"| cards | {payload['cards_total']} |",
        f"| reviews | {payload['reviews_total']} |",
        f"| searches | {payload['searches_total']} |",
        f"| recalls | {payload['recalls_total']} |",
        f"| embedding | {payload['embedding_provider']} · {payload['embedding_model']} · dim {payload['embedding_dim']} |",
        f"| vector | {payload['vector_provider']} |",
        f"| relation | {payload['relation_provider']} |",
        f"| sync | {'enabled' if payload['sync_enabled'] else 'disabled'} |",
    ]
    return "\n".join(lines) + "\n"


# ────────── read ──────────

def fmt_read(payload: dict) -> str:
    if payload.get("type") == "card":
        return _fmt_read_card(payload["card"])
    if payload.get("type") == "session":
        return _fmt_read_session(payload["session"])
    return fmt_error(f"unknown read response type: {payload.get('type')!r}")


def _fmt_read_card(card: dict) -> str:
    parts: list[str] = [f"# CARD `{card['card_id']}`", ""]
    parts.append(f"**Insight:** {card['insight']}")
    parts.append("")
    parts.append(_fmt_stats_inline(card.get("stats", {})))
    parts.append("")

    if card.get("source_cards"):
        parts.append("**From:**")
        parts.append("")
        for sc in card["source_cards"]:
            parts.append(f"- `{sc['relation']}` → `{sc['card_id']}`")
        parts.append("")

    reviews = card.get("reviews") or []
    if reviews:
        parts.append(f"## reviews ({len(reviews)})")
        parts.append("")
        for r in reviews:
            score = r["score"]
            marker = f"**+{score}**" if score > 0 else (f"**{score}**" if score < 0 else "**0**")
            line = f"- {marker} `{r['session_id']}` #{r['indexes']}"
            if r.get("comment"):
                line += f" — {r['comment']}"
            parts.append(line)
        parts.append("")

    rounds = card.get("rounds") or []
    if rounds:
        parts.append(f"## rounds ({len(rounds)})")
        parts.append("")
        for i, r in enumerate(rounds):
            head = f"**[`{r['session_id']}`#{r['index']} {r['role']}]**"
            parts.append(head)
            parts.append("")
            parts.append(r.get("text") or "")
            if i < len(rounds) - 1:
                parts.append("")
                parts.append("---")
                parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _fmt_stats_inline(stats: dict) -> str:
    up = stats.get("review_up", 0)
    down = stats.get("review_down", 0)
    rc = stats.get("review_count", 0)
    rd = stats.get("read_count", 0)
    rcl = stats.get("recall_count", 0)
    return f"**Stats:** ↑{up} ↓{down} · reviews {rc} · reads {rd} · recalls {rcl}"


def _fmt_read_session(session: dict) -> str:
    parts: list[str] = [f"# SESSION `{session['session_id']}`", ""]
    if session.get("created_at"):
        parts.append(f"**Created:** `{session['created_at']}`")
        parts.append("")
    if session.get("metadata"):
        parts.append("**Metadata:**")
        parts.append("")
        for k, v in sorted(session["metadata"].items()):
            parts.append(f"- {k}: `{v}`")
        parts.append("")
    if session.get("source"):
        parts.append(f"**Source:** {session['source']}")
        parts.append("")

    rounds = session.get("rounds") or []
    parts.append(f"## rounds ({len(rounds)})")
    parts.append("")
    for i, r in enumerate(rounds):
        parts.append(f"**[#{r['index']} {r.get('role') or ''}]**")
        parts.append("")
        text = _flatten_blocks(r.get("content") or [])
        parts.append(text)
        if i < len(rounds) - 1:
            parts.append("")
            parts.append("---")
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _flatten_blocks(blocks: list[Any]) -> str:
    out: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("text") or b.get("thinking")
        if t:
            out.append(str(t))
            continue
        ttype = b.get("type") or "block"
        out.append(f"_({ttype})_")
    return "\n\n".join(out)


# ────────── sync ──────────

def fmt_sync_status(payload: dict) -> str:
    status = payload.get("status", "")
    if status == "disabled":
        return (
            "# sync · **disabled**\n\n"
            "hint: enable via `memory-talk setup` or set `sync.enabled` "
            "in `settings.json` and restart the server.\n"
        )
    if status == "error":
        err = payload.get("error") or "unknown error"
        return f"# sync · **error**\n\n{err}\n"

    # running
    phase = payload.get("phase") or "watching"
    secs = int(payload.get("uptime_seconds") or 0)
    adapters = ", ".join(payload.get("adapters") or [])
    totals = payload.get("totals") or {}
    watching = payload.get("watching") or []

    lines = [
        f"# sync · **running** · phase `{phase}`", "",
        "| field | value |", "|---|---|",
        f"| uptime | {_humanize_secs(secs)} |",
        f"| adapters | {adapters} |",
    ]
    paths = []
    for w in watching:
        marker = "" if w.get("ok") else f" ({w.get('reason') or 'missing'})"
        paths.append(f"`{w['path']}`{marker}")
    lines.append(f"| watching | {', '.join(paths) if paths else '—'} |")
    lines.append(f"| imported | {totals.get('imported', 0)} |")
    lines.append(f"| appended | {totals.get('appended', 0)} |")
    lines.append(f"| overwrite_warnings | {totals.get('overwrite_warnings', 0)} |")
    lines.append(f"| errors | {totals.get('errors', 0)} |")
    lines.append(f"| last_event_at | {payload.get('last_event_at') or '—'} |")

    recent = payload.get("recent") or []
    if recent:
        lines.extend(["", "## recent", "", "| time | session_id | event | rounds |", "|---|---|---|---|"])
        for ev in recent:
            rounds = ev.get("rounds")
            if rounds is None and ev.get("rounds_skipped") is not None:
                rounds = f"(-{ev['rounds_skipped']} skipped)"
            lines.append(f"| {ev['at']} | `{ev['session_id']}` | {ev['event']} | {rounds if rounds is not None else '—'} |")

    return "\n".join(lines) + "\n"


# ────────── card ──────────

def fmt_card_created(payload: dict) -> str:
    return f"ok: created `{payload['card_id']}`\n"


# ────────── review ──────────

def fmt_review_created(payload: dict) -> str:
    score = payload.get("score", 0)
    score_str = f"+{score}" if score > 0 else str(score)
    return (
        f"ok: created `{payload['review_id']}` · "
        f"`{payload['card_id']}` **{score_str}** "
        f"by `{payload['session_id']}`\n"
    )


# ────────── recall ──────────

def fmt_recall(payload: dict) -> str:
    """Bash-code-block layout: one ``memory-talk read <cid> # <insight>`` per
    recalled card. Empty recall → empty string (the harness injects nothing).

    Designed so the harness can inline this directly into an LLM's context
    — the bash block tells the model these are runnable expansion commands
    without adding any business-layer headers/footers.
    """
    recalled = payload.get("recalled") or []
    if not recalled:
        return ""
    lines = ["```bash", "# Relevant memories — run any to expand detail:"]
    for r in recalled:
        lines.append(f"memory-talk read {r['card_id']}  # {r['insight']}")
    lines.append("```")
    return "\n".join(lines) + "\n"


# ────────── search ──────────

def fmt_search(payload: dict) -> str:
    query = payload.get("query") or ""
    count = payload.get("count", 0)
    sid = payload.get("search_id", "")
    parts: list[str] = [f"# search: {query}" if query else "# search",
                        "",
                        f"`search_id={sid}` · {count} results", ""]

    if count == 0:
        return "\n".join(parts) + "\n"

    for entry in payload.get("results") or []:
        parts.append("---")
        parts.append("")
        if entry.get("type") == "card":
            parts.append(_fmt_search_card(entry))
        elif entry.get("type") == "session":
            parts.append(_fmt_search_session(entry))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _fmt_search_card(entry: dict) -> str:
    stats = entry.get("stats") or {}
    inline = (
        f"`↑{stats.get('review_up', 0)} ↓{stats.get('review_down', 0)} · "
        f"reviews {stats.get('review_count', 0)} · "
        f"reads {stats.get('read_count', 0)} · "
        f"recalls {stats.get('recall_count', 0)}`"
    )
    return (
        f"### [CARD] `{entry['card_id']}` · {inline}\n\n"
        f"{entry.get('insight', '')}"
    )


def _fmt_search_session(entry: dict) -> str:
    head = (
        f"### [SESSION] `{entry['session_id']}` · "
        f"{entry.get('source', '')} · {entry.get('hit_count', 0)} hits"
    )
    lines: list[str] = [head, ""]
    for hit in entry.get("hits") or []:
        role = hit.get("role") or ""
        lines.append(f"**#{hit['index']}** _({role})_")
        ctx_before = hit.get("context_before")
        ctx_after = hit.get("context_after")
        if ctx_before:
            lines.append(f"> _[{ctx_before['index']}] {ctx_before['text']}_")
        lines.append(f"> [{hit['index']}] {hit.get('text') or ''}")
        if ctx_after:
            lines.append(f"> _[{ctx_after['index']}] {ctx_after['text']}_")
        lines.append("")
    return "\n".join(lines).rstrip()


# ────────── helpers ──────────

def _humanize_secs(s: int) -> str:
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}h {m}m"

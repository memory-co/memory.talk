"""Markdown formatters — one ``fmt_<cmd>`` per command output shape.

Each formatter takes the parsed JSON payload and returns Markdown text
that ``_render.emit_md()`` ships to stdout. The Markdown matches the
contract in docs/cli/v3/<cmd>.md exactly — adjust the contract first,
then the formatter.
"""
from __future__ import annotations
import re
from typing import Any


# ``**word**`` inline-bold markers (from server-side make_snippet). Used
# only to strip them out when we render inside a code fence — see the
# trade-off note above ``_fmt_search_session``.
_INLINE_BOLD = re.compile(r"\*\*(.+?)\*\*", flags=re.DOTALL)


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


def fmt_server_restart(payload: dict) -> str:
    status = payload.get("status", "")
    if status == "restarted":
        return (
            f"**restarted** · prev pid `{payload.get('previous_pid')}` "
            f"→ pid `{payload['pid']}` · port `{payload['port']}`\n"
        )
    if status == "started":
        # No previous daemon — restart degenerated into a fresh start.
        return (
            f"**started** · pid `{payload['pid']}` · port `{payload['port']}` "
            "(was not running)\n"
        )
    if status == "failed":
        # Reuse start's failure shape — same fields are populated.
        return fmt_server_start(payload)
    return f"**{status}**\n"


def fmt_status(payload: dict) -> str:
    if payload.get("status") == "not_running":
        return (
            "# memory.talk · **not_running**\n\n"
            f"- data_root: `{payload.get('data_root', '')}`\n"
            f"- settings: `{payload.get('settings_path', '')}`\n"
        )
    lines = [
        "# memory.talk · **running**",
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
        out = (
            "# sync · **disabled**\n\n"
            "hint: enable via `memory.talk setup` or set `sync.enabled` "
            "in `settings.json` and restart the server.\n"
        )
        # Index health is meaningful even when sync is off — if the
        # last run left a backlog, the user should know now (not later
        # when search starts missing things).
        idx_block = _fmt_index_health(payload.get("index"))
        return out + (idx_block or "")
    if status == "error":
        err = payload.get("error") or "unknown error"
        return f"# sync · **error**\n\n{err}\n" + (_fmt_index_health(payload.get("index")) or "")

    # running
    phase = payload.get("phase") or "watching"
    secs = int(payload.get("uptime_seconds") or 0)
    totals = payload.get("totals") or {}
    endpoints = payload.get("endpoints") or []
    totals_by_endpoint = payload.get("totals_by_endpoint") or {}

    lines = [
        f"# sync · **running** · phase `{phase}`", "",
        "| field | value |", "|---|---|",
        f"| uptime | {_humanize_secs(secs)} |",
        f"| endpoints | {len(endpoints)} |",
        f"| imported | {totals.get('imported', 0)} |",
        f"| appended | {totals.get('appended', 0)} |",
        f"| errors | {totals.get('errors', 0)} |",
        f"| index_errors | {totals.get('index_errors', 0)} |",
        f"| last_event_at | {payload.get('last_event_at') or '—'} |",
    ]

    if endpoints:
        # Per-endpoint table — one row per (source, location). Folds
        # in totals_by_endpoint so the user sees both reachability +
        # ingest activity per endpoint at a glance.
        lines.extend([
            "", "## endpoints", "",
            "| source | location | ok | imported | appended | errors |",
            "|---|---|---|---|---|---|",
        ])
        for ep in endpoints:
            key = f"{ep['source']}@{ep.get('label') or ep.get('location')}"
            t = totals_by_endpoint.get(key) or {}
            mark = "✓" if ep.get("ok") else f"✗ ({ep.get('reason') or 'missing'})"
            lines.append(
                f"| {ep['source']} | `{ep.get('location') or '—'}` | "
                f"{mark} | {t.get('imported', 0)} | {t.get('appended', 0)} | "
                f"{t.get('errors', 0)} |"
            )

    idx_block = _fmt_index_health(payload.get("index"))
    if idx_block:
        lines.append("")
        lines.append(idx_block.rstrip())

    recent = payload.get("recent") or []
    if recent:
        lines.extend(["", "## recent", "", "| time | session_id | event | rounds |", "|---|---|---|---|"])
        for ev in recent:
            rounds = ev.get("rounds")
            if rounds is None and ev.get("rounds_skipped") is not None:
                rounds = f"(-{ev['rounds_skipped']} skipped)"
            elif rounds is None and ev.get("event") in ("index_partial", "index_failed"):
                # Embed the index-failure counts in the rounds column so
                # the existing 4-col layout still fits.
                indexed = ev.get("indexed") or 0
                failed = ev.get("index_failed") or 0
                rounds = f"+{indexed} indexed / {failed} failed"
            lines.append(f"| {ev['at']} | `{ev['session_id']}` | {ev['event']} | {rounds if rounds is not None else '—'} |")

    return "\n".join(lines) + "\n"


def _fmt_index_health(index: dict | None) -> str | None:
    """Render the index-health snapshot block. Returns None when there's
    no data (no sessions ingested yet) so callers can omit the section
    entirely on a fresh install."""
    if not index:
        return None
    total_sessions = int(index.get("total_sessions") or 0)
    if total_sessions == 0:
        return None
    total_rounds   = int(index.get("total_rounds")   or 0)
    indexed_rounds = int(index.get("indexed_rounds") or 0)
    missing        = int(index.get("missing_rounds") or 0)
    degraded       = int(index.get("degraded_sessions") or 0)
    backfill       = index.get("backfill_status") or "idle"
    last_err       = index.get("last_index_error")

    lines = [
        "## index health", "",
        "| field | value |", "|---|---|",
        f"| sessions | {total_sessions} (degraded: **{degraded}**) |"
        if degraded
        else f"| sessions | {total_sessions} |",
        f"| rounds | {total_rounds} (indexed: {indexed_rounds}, missing: **{missing}**) |"
        if missing
        else f"| rounds | {total_rounds} (all indexed) |",
        f"| backfill | `{backfill}` |",
    ]
    if last_err:
        lines.append(f"| last_index_error | `{last_err[:80]}{'…' if len(last_err) > 80 else ''}` |")

    by_endpoint = index.get("by_endpoint") or []
    if len(by_endpoint) > 1:
        # Only render the breakdown when there's something to compare —
        # a single-endpoint install (e.g. just claude-code) already saw
        # those numbers in the cross-endpoint summary above.
        lines.extend([
            "", "### by endpoint", "",
            "| endpoint | sessions | rounds | indexed | missing | degraded |",
            "|---|---|---|---|---|---|",
        ])
        for r in by_endpoint:
            lines.append(
                f"| `{r.get('endpoint') or r.get('source')}` | "
                f"{r.get('sessions', 0)} | {r.get('rounds', 0)} | "
                f"{r.get('indexed', 0)} | {r.get('missing', 0)} | "
                f"{r.get('degraded', 0)} |"
            )
    return "\n".join(lines) + "\n"


# ────────── card ──────────

def fmt_card_created(payload: dict) -> str:
    return f"ok: created `{payload['card_id']}`\n"


# ────────── recall ──────────

def fmt_recall(payload: dict) -> str:
    """Bash-code-block layout: one ``memory.talk read <cid> # <insight>`` per
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
        lines.append(f"memory.talk read {r['card_id']}  # {r['insight']}")
    lines.append("```")
    return "\n".join(lines) + "\n"


def fmt_recall_sessions(payload: dict) -> str:
    """``recall list`` Markdown: per-session table, most-recent first."""
    sessions = payload.get("sessions") or []
    if not sessions:
        return "# recall · no recall history\n"
    lines = [
        f"# recall · **{len(sessions)} session{'s' if len(sessions) != 1 else ''}**",
        "",
        "| session_id | recalls | unique cards | last recall |",
        "|---|---|---|---|",
    ]
    for s in sessions:
        lines.append(
            f"| `{s['session_id']}` | {s['recalls']} | "
            f"{s['unique_cards']} | {s['last_recall']} |"
        )
    return "\n".join(lines) + "\n"


def fmt_recall_read(payload: dict) -> str:
    """``recall read <sid>`` Markdown: timeline of recall events."""
    sid = payload.get("session_id") or ""
    events = payload.get("events") or []
    if not events:
        return f"# recall · `{sid}` — no recall history\n"

    first_ts = events[0]["ts"]
    last_ts = events[-1]["ts"]
    lines = [
        f"# recall · `{sid}`",
        "",
        f"**{len(events)} event{'s' if len(events) != 1 else ''}** · "
        f"first {first_ts} · last {last_ts}",
    ]
    for i, ev in enumerate(events, start=1):
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"## [{i}] {ev['ts']}")
        lines.append("")
        lines.append(f"> {ev['prompt']}")
        lines.append("")
        returned = ev.get("returned") or []
        if returned:
            lines.append("**returned**:")
            for c in returned:
                insight = c.get("insight") or "_(no insight)_"
                lines.append(f"- `{c['card_id']}`  {insight}")
        else:
            lines.append("**returned**: _none_ (all candidates already recalled)")
        lines.append("")
        skipped = ev.get("skipped") or []
        if skipped:
            lines.append(
                "**skipped** (already recalled this session): "
                + ", ".join(f"`{c['card_id']}`" for c in skipped)
            )
        else:
            lines.append("**skipped** (already recalled this session): _none_")
    return "\n".join(lines) + "\n"


# ────────── search ──────────

def fmt_search(payload: dict) -> str:
    query = payload.get("query") or ""
    count = payload.get("count", 0)
    sid = payload.get("search_id", "")
    header = f"`search_id={sid}` · {count} results"
    parts: list[str] = [f"# search: {query}" if query else "# search",
                        "", header, ""]

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
    time_str = _fmt_time(entry.get("created_at"))
    time_suffix = f" · {time_str}" if time_str else ""
    return (
        f"### [CARD] `{entry['card_id']}` · {inline}{time_suffix}\n\n"
        f"{entry.get('insight', '')}"
    )


# Hit-body layout: fenced code block (```...```).
#
# Why this layout (chosen over blockquote `> ` 2026-05-21):
#   - hit/context text from the server can contain real newlines
#     (multi-line code, tool output, etc.). A blockquote only quotes
#     the first line; subsequent lines fall outside and the indentation
#     visually breaks. Code blocks preserve newlines as-is.
#   - arbitrary user content (``*``, ``_``, ``[``, ...) inside a code
#     block can't accidentally trigger markdown parsing, so rendering
#     stays predictable across renderers / terminals.
#
# Cost (accepted): markdown is NOT parsed inside fences, so the
# ``**keyword**`` highlight from server-side ``make_snippet`` would
# render literally as ``**LanceDB**``. We strip the bold markers below
# so the body reads cleanly; the matched word itself stays in place,
# just without emphasis. Readers who want to see the full round (with
# match context) go to ``POST /v3/read``.
#
# Fence collision: if the hit text itself contains a run of backticks
# (e.g. it embeds a ``` fence), we open with one-longer fence so the
# wrapper isn't closed prematurely.
def _fmt_search_session(entry: dict) -> str:
    head = (
        f"### [SESSION] `{entry['session_id']}` · "
        f"{entry.get('source', '')} · {entry.get('hit_count', 0)} hits"
    )
    lines: list[str] = [head, ""]
    # Header carries only hit-level metadata (index + score + time).
    # Role used to live here as ``_(human)_``, but that was misleading:
    # the fence below contains ctx_before / hit / ctx_after rounds which
    # often have DIFFERENT roles (tool stdout, sidechain, multi-turn
    # human). Roles now live inside the fence per row — see ``_round_row``.
    #
    # Score caveat: this is LanceDB's hybrid RRF combined score (FTS
    # rank + vector rank fused), NOT a similarity in [0,1]. Typical
    # top hits land around 0.01–0.03; a low score doesn't necessarily
    # mean a weak match, just a lower combined rank. Provenance
    # (FTS vs vector) is not preserved by RRF — see
    # docs/structure/v3/search-result.md.
    #
    # Adjacency merging: hits whose context windows overlap (|idx_diff|
    # ≤ 2 with the current ±1 context radius) get merged into one fence
    # so the same round isn't rendered twice. The merged header lists
    # every constituent hit (``#4, #5``) and uses the top-scoring hit's
    # score / time as the anchor. Each original hit's main row keeps
    # its ``*`` marker; pure-context rows don't get one.
    for group in _merge_hits(entry.get("hits") or []):
        lines.extend(_fmt_hit_group(group))
    return "\n".join(lines).rstrip()


# Two hits are "adjacent" when their context windows touch or overlap.
# Context radius is ±1 (one round before + one round after the hit), so
# windows touch when ``idx_diff <= 2 * radius = 2``. Hardcoded because
# the context radius itself is hardcoded in ``service/search.py``
# (``_CONTEXT_TRUNCATE`` controls truncation length, not window radius;
# the ±1 sits inline in ``_build_session_result``). If radius ever
# becomes configurable, expose this too.
_MERGE_GAP = 2


def _merge_hits(hits: list[dict]) -> list[list[dict]]:
    """Group hits whose context windows overlap so they share one fence.

    Input is the API's ``hits[]`` (sorted by score, not index). Output
    is a list of groups, each a list of hits in **index order**. The
    group list itself is sorted by the top-scoring hit per group
    (descending) so the strongest group renders first — matches the
    user's mental model of "best hit first".
    """
    if not hits:
        return []
    by_idx = sorted(hits, key=lambda h: h["index"])
    groups: list[list[dict]] = [[by_idx[0]]]
    for h in by_idx[1:]:
        if h["index"] - groups[-1][-1]["index"] <= _MERGE_GAP:
            groups[-1].append(h)
        else:
            groups.append([h])
    # Re-sort groups by their strongest hit so the page leads with the
    # most relevant one.
    groups.sort(
        key=lambda g: max((h.get("score") or 0.0) for h in g),
        reverse=True,
    )
    return groups


def _fmt_hit_group(group: list[dict]) -> list[str]:
    """Render one group — single hit reuses the original layout; multi
    hits merge ctx_before / hit / ctx_after rounds into one fence with
    every constituent hit's main row marked ``*``."""
    # ── header ──────────────────────────────────────────────────────
    top = max(group, key=lambda h: h.get("score") or 0.0)
    idx_label = ", ".join(f"#{h['index']}" for h in group)
    score_suffix = (
        f" · top score `{top['score']:.4f}`" if len(group) > 1
        else (f" · score `{top['score']:.4f}`" if top.get("score") is not None else "")
    )
    time_str = _fmt_time(top.get("timestamp"))
    time_suffix = f" · {time_str}" if time_str else ""
    header = f"**{idx_label}**{score_suffix}{time_suffix}"

    # ── body: union of (ctx_before, hit, ctx_after) across group ────
    # Hit version wins over context version on idx collision (richer
    # snippet text from server-side ``make_snippet`` vs simple truncate).
    hit_indices = {h["index"] for h in group}
    rounds_by_idx: dict[int, dict] = {}
    # Pass 1: hits (these win).
    for h in group:
        rounds_by_idx[h["index"]] = h
    # Pass 2: contexts (don't overwrite hits).
    for h in group:
        for key in ("context_before", "context_after"):
            ctx = h.get(key)
            if ctx and ctx["index"] not in rounds_by_idx:
                rounds_by_idx[ctx["index"]] = ctx

    body = "\n".join(
        _round_row(rounds_by_idx[i], is_hit=(i in hit_indices))
        for i in sorted(rounds_by_idx)
    )
    fence = _pick_fence(body)
    return [header, fence, body, fence, ""]


# CLI-only role display mapping. Server-side role strings stay as
# ``assistant`` / ``human`` / ``tool`` / ``system`` (see schemas /
# search-result.md); we only remap at render time for screen real-estate
# and idiom — ``AI`` reads faster than ``ASSISTANT`` and matches how
# users talk about Claude/GPT outputs in casual conversation.
_ROLE_DISPLAY = {
    "ASSISTANT": "AI",
}


def _round_row(round_dict: dict, *, is_hit: bool) -> str:
    """Render one round line for the search-hit fence.

    Layout: ``[<idx> <ROLE>[*]] <text>``. The hit row gets a trailing
    ``*`` inside the brackets so the marker sits in the same column band
    as the role tag — every line still starts at column 0, all ``[…]``
    prefixes left-align, so the eye scans cleanly even with mixed roles.

    Role is uppercased and then passed through ``_ROLE_DISPLAY`` for
    CLI-only remapping (``ASSISTANT`` → ``AI``); the underlying API /
    storage value is unchanged.
    """
    raw = (round_dict.get("role") or "").upper()
    role = _ROLE_DISPLAY.get(raw, raw)
    marker = "*" if is_hit else ""
    tag = f"[{round_dict['index']} {role}{marker}]" if role else f"[{round_dict['index']}{marker}]"
    return f"{tag} {_inline_text(round_dict.get('text') or '')}"


def _strip_bold(text: str) -> str:
    """Unwrap ``**…**`` markers — they'd render literally inside a code fence."""
    return _INLINE_BOLD.sub(r"\1", text)


def _inline_text(text: str) -> str:
    """Render a round's text as a single line inside the code fence.

    Search hit / context text often contains real newlines (multi-line
    code, tool stdout, paragraph breaks). Inside the fence those
    newlines preserve correctly but visually break the "one round =
    one ``[N] ...`` line" structure — long multi-line rounds bleed into
    each other and you lose the ability to scan. Flatten ``\\n`` to a
    single space so each round renders on its own line and the terminal
    handles soft-wrapping. The full round (with structure) is still one
    ``POST /v3/read`` away.

    Also strips the ``**...**`` highlight markers (markdown isn't parsed
    inside fences, so they'd show literally).
    """
    return _strip_bold(text).replace("\r\n", " ").replace("\n", " ")


def _pick_fence(body: str) -> str:
    """Pick a backtick run long enough to not collide with body content."""
    longest_run = 0
    current = 0
    for ch in body:
        if ch == "`":
            current += 1
            if current > longest_run:
                longest_run = current
        else:
            current = 0
    return "`" * max(3, longest_run + 1)


# ────────── helpers ──────────

def _humanize_secs(s: int) -> str:
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}h {m}m"


def _fmt_time(iso_str: str | None) -> str:
    """Render a UTC ISO 8601 timestamp as ``YYYY-MM-DD HH:MM (N <unit>前)``.

    Absolute portion is converted to local time so the reader sees their
    wall clock. Relative portion uses Chinese suffix and rolls up by
    largest fitting unit (minute → hour → day → month → year). Returns
    empty string for None/unparseable input so callers can just append
    without guarding.
    """
    if not iso_str:
        return ""
    import datetime as _dt
    try:
        s = iso_str.replace("Z", "+00:00")
        dt = _dt.datetime.fromisoformat(s)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.UTC)
    now = _dt.datetime.now(_dt.UTC)
    delta_sec = max(0, int((now - dt).total_seconds()))

    def _plural(n: int, unit: str) -> str:
        return f"{n} {unit}{'s' if n != 1 else ''} ago"

    if delta_sec < 60:
        rel = "just now"
    elif delta_sec < 3600:
        rel = _plural(delta_sec // 60, "minute")
    elif delta_sec < 86400:
        rel = _plural(delta_sec // 3600, "hour")
    elif delta_sec < 86400 * 30:
        rel = _plural(delta_sec // 86400, "day")
    elif delta_sec < 86400 * 365:
        rel = _plural(delta_sec // (86400 * 30), "month")
    else:
        rel = _plural(delta_sec // (86400 * 365), "year")

    local = dt.astimezone()
    abs_str = local.strftime("%Y-%m-%d %H:%M")
    return f"{abs_str} ({rel})"


# ────────── session list / tag ──────────

def fmt_session_list(payload: dict, filter_summary: str = "") -> str:
    """Render ``GET /v3/sessions`` as H3-per-result blocks.

    Mirrors search.md / docs/cli/v3/session.md exactly:
      - top header line
      - filter echo + N / TOTAL on the second line
      - one `### [SESSION] ...` block per row, `---` between them
      - footer hint when total > returned
    """
    total = int(payload.get("total") or 0)
    returned = int(payload.get("returned") or 0)
    sessions = payload.get("sessions") or []

    lines = ["# session list", ""]
    if filter_summary:
        lines.append(f"`filter: {filter_summary}` · {returned} / {total} results")
    else:
        lines.append(f"{returned} / {total} results")
    lines.append("")

    for s in sessions:
        sid = s.get("session_id") or "?"
        src = s.get("source") or "?"
        rc = int(s.get("round_count") or 0)
        lines.append("---")
        lines.append("")
        lines.append(f"### [SESSION] `{sid}` · {src} · {rc} rounds")
        lines.append("")
        lines.append(_session_meta_line(s))
        lines.append("")

    if total > returned:
        lines.append("---")
        lines.append("")
        lines.append(
            f"_(showing {returned} of {total} — pass --limit higher to see more)_"
        )
    return "\n".join(lines).rstrip() + "\n"


def fmt_session_tag(payload: dict, *, is_query: bool) -> str:
    """Render PATCH /v3/sessions/<sid>/tags response.

    `is_query` is True when the CLI sent an empty body (no K=V / -K) —
    output a query table; otherwise output the one-line "ok: …" confirm.
    """
    sid = payload.get("session_id") or "?"
    tags = payload.get("tags") or {}

    if is_query:
        if not tags:
            return "(no tags)\n"
        lines = [f"# {sid} · tags", "", "| key | value |", "|---|---|"]
        for k in sorted(tags):
            lines.append(f"| {k} | {tags[k]} |")
        return "\n".join(lines) + "\n"

    if not tags:
        return f"ok: `{sid}` · tags cleared\n"
    pretty = " ".join(f"{k}={tags[k]}" for k in sorted(tags))
    return f"ok: `{sid}` · tags = `{pretty}`\n"


def _session_meta_line(s: dict) -> str:
    """Build the single-line metadata strip under each session H3.

    Format:  `tags: K=V K=V` · `cwd: <path>` · 2026-05-24 09:12 (1 day ago)

    Each segment is conditionally included — empty tags / missing cwd
    are silently dropped so the line doesn't have stray ``—`` markers.
    """
    parts: list[str] = []
    tags = s.get("tags") or {}
    if tags:
        kv = " ".join(f"{k}={tags[k]}" for k in sorted(tags))
        parts.append(f"`tags: {kv}`")
    cwd = s.get("cwd")
    if cwd:
        parts.append(f"`cwd: {_shorten_cwd(cwd)}`")
    when = _fmt_time(s.get("created_at"))
    if when:
        parts.append(when)
    return " · ".join(parts) if parts else "_(no metadata)_"


# ────────── card list / tag ──────────

def fmt_card_list(payload: dict, filter_summary: str = "") -> str:
    """Render ``GET /v3/cards`` as H3-per-result blocks.

    Mirrors docs/cli/v3/card.md exactly and stays visually aligned
    with ``fmt_search`` ``[CARD]`` blocks so list + search outputs
    read consistently:

      - top header line
      - filter echo + N / TOTAL on the second line
      - one ``### [CARD]`` block per row with inline stats
      - insight as a paragraph, then a tags + time metadata line
      - footer hint when total > returned
    """
    total = int(payload.get("total") or 0)
    returned = int(payload.get("returned") or 0)
    cards = payload.get("cards") or []

    lines = ["# card list", ""]
    if filter_summary:
        lines.append(f"`filter: {filter_summary}` · {returned} / {total} results")
    else:
        lines.append(f"{returned} / {total} results")
    lines.append("")

    for c in cards:
        cid = c.get("card_id") or "?"
        stats = c.get("stats") or {}
        stats_str = (
            f"↑{stats.get('review_up', 0)} ↓{stats.get('review_down', 0)} · "
            f"reviews {stats.get('review_count', 0)} · "
            f"reads {stats.get('read_count', 0)} · "
            f"recalls {stats.get('recall_count', 0)}"
        )
        lines.append("---")
        lines.append("")
        lines.append(f"### [CARD] `{cid}` · `{stats_str}`")
        lines.append("")
        lines.append(c.get("insight") or "")
        lines.append("")
        lines.append(_card_meta_line(c))
        lines.append("")

    if total > returned:
        lines.append("---")
        lines.append("")
        lines.append(
            f"_(showing {returned} of {total} — pass --limit higher to see more)_"
        )
    return "\n".join(lines).rstrip() + "\n"


def fmt_card_delete(payload: dict) -> str:
    """Render DELETE /v3/cards/<cid> response.

    One-line confirmation + a hint about inbound-ref dangling when
    applicable. We deliberately don't moan about every detail (vector
    cleared / files cleared / etc.) — those are best-effort and
    typically silent."""
    cid = payload.get("card_id") or "?"
    dangling = int(payload.get("inbound_refs_dangling", 0) or 0)

    bits = [f"deleted · `{cid}`"]
    if dangling:
        bits.append(
            f"⚠ {dangling} inbound `source_cards` reference"
            f"{'s' if dangling != 1 else ''} now dangling",
        )
    return " · ".join(bits) + "\n"


def fmt_card_tag(payload: dict, *, is_query: bool) -> str:
    """Render PATCH /v3/cards/<cid>/tags response.

    `is_query` is True when the CLI sent an empty body — output a
    query table; otherwise output the one-line "ok: …" confirm.
    """
    cid = payload.get("card_id") or "?"
    tags = payload.get("tags") or {}

    if is_query:
        if not tags:
            return "(no tags)\n"
        lines = [f"# {cid} · tags", "", "| key | value |", "|---|---|"]
        for k in sorted(tags):
            lines.append(f"| {k} | {tags[k]} |")
        return "\n".join(lines) + "\n"

    if not tags:
        return f"ok: `{cid}` · tags cleared\n"
    pretty = " ".join(f"{k}={tags[k]}" for k in sorted(tags))
    return f"ok: `{cid}` · tags = `{pretty}`\n"


def _card_meta_line(c: dict) -> str:
    """Build the single-line metadata strip under each card H3:
       `tags: ...` · 2026-05-24 09:12 (1 day ago)"""
    parts: list[str] = []
    tags = c.get("tags") or {}
    if tags:
        kv = " ".join(f"{k}={tags[k]}" for k in sorted(tags))
        parts.append(f"`tags: {kv}`")
    when = _fmt_time(c.get("created_at"))
    if when:
        parts.append(when)
    return " · ".join(parts) if parts else "_(no metadata)_"


def _shorten_cwd(path: str, *, max_len: int = 60) -> str:
    """``$HOME/...`` → ``~/...``; long paths get a middle ellipsis.
    Pure cosmetic — doesn't affect the underlying field."""
    import os
    home = os.path.expanduser("~")
    if home and path.startswith(home):
        path = "~" + path[len(home):]
    if len(path) <= max_len:
        return path
    head = path[: max_len // 2 - 1]
    tail = path[-(max_len // 2 - 1):]
    return f"{head}…{tail}"

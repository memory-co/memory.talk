"""``session mark`` helpers — submission loading, rendering, interactive flow.

Kept out of ``cli/session.py`` so the (chunky) interactive loop and YAML
parsing don't crowd the list/tag commands. See ``docs/cli/v4/session.md``.

Two paths, one endpoint
=======================
Both the YAML batch path (``--mark <file>`` / stdin) and the interactive
step-through ("step 标注") build the SAME submission body and POST it once
to the existing ``POST /v4/sessions/{sid}/marks``. The interactive path is
a *client-side* walk: a 2-round sliding window rendered with ``rich.Panel``,
marks typed via ``questionary.text(multiline=True)``, accumulated locally
with monotonic ``m<n>`` ids, then batched at the end. No server-side draft
state, no new endpoint — see ``docs/works/v4/session-mark-tui.md`` §3/§4.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional

import click
import yaml

from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.config import Config
from memorytalk.util.ids import MARK_SEQ_PREFIX, mark_seq


# ────────── file / pipe mode ──────────

def load_submission(path: str) -> dict:
    """Load a submission YAML (``-`` = stdin) into a request body dict.

    Validates the wire shape only (``last_index`` / ``description`` /
    non-empty ``marks`` with ``id``); the server owns the deep rules
    (optimistic lock, monotonic ids, #…？ → indexes). Raises
    ``click.BadParameter`` / ``ValueError`` on a malformed file.
    """
    if path == "-":
        raw = sys.stdin.read()
    else:
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            raise click.BadParameter(f"cannot read --mark file {path!r}: {e}")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML: {e}")
    if not isinstance(data, dict):
        raise ValueError("invalid YAML: expected a mapping at the top level")
    if "last_index" not in data:
        raise ValueError("last_index required")
    marks = data.get("marks")
    if not isinstance(marks, list) or not marks:
        raise ValueError("marks required")
    body = {
        "last_index": data["last_index"],
        "description": data.get("description") or "",
        "marks": [],
    }
    for m in marks:
        if not isinstance(m, dict) or not m.get("id"):
            raise ValueError("each mark needs an explicit id (m<n>)")
        entry = {"id": m["id"], "mark": m.get("mark") or ""}
        if m.get("indexes") is not None:
            entry["indexes"] = str(m["indexes"])
        body["marks"].append(entry)
    return body


# ────────── rendering ──────────

def fmt_mark_result(result: dict) -> str:
    """Render a submit response (which #…？ became new/linked cards)."""
    sid = result.get("session_id", "")
    last_index = result.get("last_index", "")
    lines = [f"✓ marked `{sid}` · last_index {last_index}", ""]
    for m in result.get("marks", []):
        issues = m.get("issues") or []
        if not issues:
            lines.append(f"- `{m['mark']}`  (no issues)")
            continue
        for iss in issues:
            tag = "new card" if iss.get("is_new") else "linked"
            lines.append(
                f"- `{m['mark']}`  #{iss['issue']}？  → {tag} `{iss['card_id']}`"
            )
    return "\n".join(lines).rstrip() + "\n"


# ────────── interactive mode: round rendering ──────────

_MAX_ROUND_CHARS = 1200


def _round_text(r: dict) -> str:
    """Flatten a round's content blocks into plain text."""
    blocks = r.get("content") or []
    out = []
    for b in blocks:
        if isinstance(b, dict):
            t = b.get("text") or b.get("thinking")
            if t:
                out.append(str(t))
    text = "\n".join(out).strip()
    if len(text) > _MAX_ROUND_CHARS:
        text = text[:_MAX_ROUND_CHARS].rstrip() + " …"
    return text


def _speaker(r: dict) -> str:
    return str(r.get("role") or r.get("speaker") or "?")


def render_window(prev: Optional[dict], cur: dict) -> str:
    """Render the 2-round window as text using ``rich.Panel``.

    ``prev`` (context, dim) sits above ``cur`` (current, highlighted —
    "标这里"). When there's no prev (first round / single-round session)
    only the current panel is shown. Returns the rendered string so the
    caller can echo it (and tests can assert on it) without forcing a TTY.
    """
    from rich.console import Console
    from rich.panel import Panel

    console = Console(file=None, record=True, width=88)
    if prev is not None:
        console.print(Panel(
            f"[dim]\\[{_speaker(prev)}] {_round_text(prev)}[/dim]",
            title=f"round {prev['index']} · context",
            title_align="left", border_style="dim",
        ))
    console.print(Panel(
        f"\\[{_speaker(cur)}] {_round_text(cur)}",
        title=f"round {cur['index']} · current · 标这里",
        title_align="left", border_style="cyan",
    ))
    return console.export_text()


# ────────── interactive mode: input seam ──────────

# An input seam is a tiny callable injected into the walk so tests can drive
# the loop deterministically without a real terminal. Production uses
# ``questionary`` (prompt_toolkit under the hood); tests pass a scripted
# function. ``ask_description`` returns the one-time scene string;
# ``ask_mark`` returns the per-round mark text / command (blank / :back / :q).
AskDescription = Callable[[], str]
AskMark = Callable[[dict], str]


def _questionary_description() -> str:
    import questionary
    ans = questionary.text("description (scenario; blank ok):").ask()
    # ask() returns None on Ctrl-C / Ctrl-D — treat as empty.
    return (ans or "").strip()


def _questionary_mark(cur: dict) -> str:
    import questionary
    ans = questionary.text(
        f"mark round {cur['index']} "
        "(text = mark / blank = skip / :back / :q):",
        multiline=True,
    ).ask()
    if ans is None:        # Ctrl-C / Ctrl-D → behave like quit
        return ":q"
    return ans


def _max_existing_seq(cfg: Config, session_id: str) -> int:
    """Return the current max ``m<n>`` seq for the session (0 if none).

    Locally-assigned ids must continue monotonically from this so the
    server's "no skip / no reuse" rule isn't tripped on submit.
    """
    try:
        listing = api("GET", f"/v4/sessions/{session_id}/marks", cfg)
    except ApiError:
        # A fresh / unmarked session may 404 here on some backends; treat
        # any read failure as "no prior marks" — the server still enforces
        # monotonicity at submit time, so we fail safe, not silent-wrong.
        return 0
    except Exception:
        return 0
    best = 0
    for m in listing.get("marks") or []:
        mid = str(m.get("mark") or "")
        if mid.startswith(MARK_SEQ_PREFIX) and mid[len(MARK_SEQ_PREFIX):].isdigit():
            best = max(best, int(mid[len(MARK_SEQ_PREFIX):]))
    return best


def run_interactive(
    cfg: Config,
    session_id: str,
    json_out: bool,
    post_fn,
    *,
    ask_description: Optional[AskDescription] = None,
    ask_mark: Optional[AskMark] = None,
    echo: Callable[[str], None] = click.echo,
) -> dict | None:
    """Client-side step-through ("step 标注") over the batch marks endpoint.

    Walks the session round by round in a 2-round sliding window
    (``[r1,r2] → mark r2 → [r2,r3] → mark r3 → …``); ``r1`` is context-only.
    For each *current* round the user types a mark (blank = skip, ``:back``
    = step back one window, ``:q`` = quit). Marks accumulate client-side
    with monotonic ``m<n>`` ids (continued from the session's current max)
    and auto-filled ``indexes`` (the current round's own index). At the end
    the whole batch is POSTed once. Returns the submit response, or ``None``
    when nothing was collected / the user quit before submitting.

    ``last_index`` is locked once on entry (the round count when we start);
    if the session advanced meanwhile the server's optimistic lock rejects
    the batch at submit time → we surface a clean "session advanced" message.

    ``ask_description`` / ``ask_mark`` are the input seam (default:
    ``questionary``); tests inject scripted callables to drive the loop.
    """
    ask_description = ask_description or _questionary_description
    ask_mark = ask_mark or _questionary_mark

    # Pull the session's rounds via the read endpoint.
    try:
        read = api("POST", "/v4/read", cfg, json_body={"id": session_id})
    except ApiError as e:
        echo(f"error: {extract_error_message(e.payload)}")
        raise SystemExit(1)
    except Exception as e:
        echo(f"error: cannot reach server: {e}")
        raise SystemExit(1)

    session = read.get("session") or {}
    rounds = session.get("rounds") or []
    if not rounds:
        echo("session has no rounds to mark — nothing to do.")
        return None

    last_index = len(rounds)   # rounds are 1-indexed → max idx == count
    next_n = _max_existing_seq(cfg, session_id) + 1

    echo(
        f"session {session_id} · {last_index} rounds · interactive step标注 "
        "(text = mark / blank = skip / :back = back / :q = quit)"
    )
    description = ask_description()

    collected: list[dict] = []
    # Step k shows window [r_{k-1}, r_k] and marks r_k. We walk r_1..r_N so
    # every round (including the first, context-less one) is markable.
    k = 0
    try:
        while k < len(rounds):
            prev = rounds[k - 1] if k > 0 else None
            cur = rounds[k]
            echo("")
            echo(render_window(prev, cur))
            text = ask_mark(cur)
            cmd = text.strip()
            if cmd == ":q":
                break
            if cmd == ":back":
                # Step back one window; already-collected marks stay
                # (append-only — :back never un-assigns an id).
                k = max(0, k - 1)
                continue
            if cmd == "":
                k += 1
                continue
            # A non-blank mark for the current round. ``indexes`` is the
            # current round's own index (auto-filled — no manual entry).
            collected.append({
                "id": mark_seq(next_n),
                "mark": text,
                "indexes": str(cur["index"]),
            })
            next_n += 1
            k += 1
    except (KeyboardInterrupt, EOFError):
        echo("\n(interrupted)")

    if not collected:
        echo("(nothing marked)")
        return None

    body = {
        "last_index": last_index,
        "description": description,
        "marks": collected,
    }
    # ``post_fn`` (cli.session._post_marks) handles HTTP errors itself —
    # including a dedicated 409 "session advanced; re-enter" message — and
    # exits on failure, so it returns either a clean result dict or never.
    return post_fn(cfg, session_id, body, json_out)

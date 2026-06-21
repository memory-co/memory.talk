"""``session mark`` helpers — submission loading, rendering, interactive flow.

Kept out of ``cli/session.py`` so the (chunky) interactive loop and YAML
parsing don't crowd the list/tag commands. See ``docs/cli/v4/session.md``.

Two paths, one endpoint
=======================
Both the YAML batch path (``--mark <file>`` / stdin) and the interactive
step-through ("step 标注") build the SAME submission body and POST it once
to ``POST /v4/sessions/{sid}/marks``. One submission = ONE mark; the server
auto-assigns its id ``m<n>``. The interactive path is a *client-side* walk:
a 2-round sliding window rendered with ``rich.Panel``, comments typed via
``questionary.text(multiline=True)``, accumulated as per-round entries from
index 1, then submitted at the end. No server-side draft state, no new
endpoint — see ``docs/works/v4/session-mark-tui.md``.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional

import math

import click
import yaml

from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.config import Config
from memorytalk.service.session_marks import MARK_COVERAGE_THRESHOLD


# ────────── file / pipe mode ──────────

def load_submission(path: str) -> dict:
    """Load a submission YAML (``-`` = stdin) into a request body dict.

    Validates the wire shape only (``last_index`` / ``description`` /
    non-empty ``rounds`` each with an ``index``); the server owns the deep
    rules (optimistic lock, first index == 1, strictly ascending, ≥90%
    coverage, #…？ → cards). The mark id ``m<n>`` is server-assigned — the
    submission never carries it. Raises ``click.BadParameter`` / ``ValueError``
    on a malformed file.
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
    rounds = data.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        raise ValueError("rounds required")
    body = {
        "last_index": data["last_index"],
        "description": data.get("description") or "",
        "rounds": [],
    }
    for rd in rounds:
        if not isinstance(rd, dict) or rd.get("index") is None:
            raise ValueError("each round needs an integer index")
        entry: dict = {"index": rd["index"]}
        if rd.get("comment") is not None:
            entry["comment"] = str(rd["comment"])
        if rd.get("issues") is not None:
            # Pass explicit issues straight through ({issue, indexes?}); the
            # server fills card_id / is_new.
            entry["issues"] = rd["issues"]
        body["rounds"].append(entry)
    return body


# ────────── rendering ──────────

def fmt_mark_result(result: dict) -> str:
    """Render a submit response (the auto-assigned mark + which #…？ became
    new/linked cards, per round)."""
    sid = result.get("session_id", "")
    mark = result.get("mark", "")
    rounds = result.get("rounds") or []
    issues = [(rd.get("index"), iss)
              for rd in rounds for iss in (rd.get("issues") or [])]
    lines = [f"✓ marked `{sid}` · `{mark}` · {len(rounds)} round(s)", ""]
    if not issues:
        lines.append("  (no issues)")
    for idx, iss in issues:
        tag = "new card" if iss.get("is_new") else "linked"
        lines.append(
            f"  - [#{idx}] #{iss['issue']}？  → {tag} `{iss['card_id']}`"
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
# ``ask_comment`` returns the per-round comment text / command (blank / :back
# / :q).
AskDescription = Callable[[], str]
AskComment = Callable[[dict], str]


def _questionary_description() -> str:
    import questionary
    ans = questionary.text("description (scenario; blank ok):").ask()
    # ask() returns None on Ctrl-C / Ctrl-D — treat as empty.
    return (ans or "").strip()


def _questionary_comment(cur: dict) -> str:
    import questionary
    ans = questionary.text(
        f"comment round {cur['index']} "
        "(text = comment / blank = no comment / :back / :q):",
        multiline=True,
    ).ask()
    if ans is None:        # Ctrl-C / Ctrl-D → behave like quit
        return ":q"
    return ans


def run_interactive(
    cfg: Config,
    session_id: str,
    json_out: bool,
    post_fn,
    *,
    ask_description: Optional[AskDescription] = None,
    ask_comment: Optional[AskComment] = None,
    echo: Callable[[str], None] = click.echo,
) -> dict | None:
    """Client-side step-through ("step 标注") over the submit endpoint.

    Walks the session round by round from index 1 in a 2-round sliding window
    (``[r1,r2] → comment r2 → [r2,r3] → comment r3 → …``); ``r1`` is
    context-only. For each *current* round the user types a comment (blank =
    no comment but the round is still recorded → coverage; ``:back`` = step
    back one window, ``:q`` = quit). Rounds accumulate as ``{index, comment?}``
    entries. The mark id ``m<n>`` is SERVER-assigned (no client minting). At
    the end the whole submission is POSTed once. Returns the submit response,
    or ``None`` when nothing was collected / the user quit before submitting.

    ``last_index`` is locked once on entry (the round count when we start);
    if the session advanced meanwhile the server's optimistic lock rejects
    the submission → we surface a clean "session advanced" message.

    ``ask_description`` / ``ask_comment`` are the input seam (default:
    ``questionary``); tests inject scripted callables to drive the loop.
    """
    ask_description = ask_description or _questionary_description
    ask_comment = ask_comment or _questionary_comment

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

    echo(
        f"session {session_id} · {last_index} rounds · interactive step标注 "
        "(text = comment / blank = no comment / :back = back / :q = quit)"
    )
    description = ask_description()

    # collected: ordered round entries keyed by index (so :back re-walk
    # overwrites rather than duplicates). We rebuild the submission body from
    # this at the end, in ascending index order.
    collected: dict[int, dict] = {}
    k = 0
    try:
        while k < len(rounds):
            prev = rounds[k - 1] if k > 0 else None
            cur = rounds[k]
            echo("")
            echo(render_window(prev, cur))
            text = ask_comment(cur)
            cmd = text.strip()
            if cmd == ":q":
                break
            if cmd == ":back":
                k = max(0, k - 1)
                continue
            idx = int(cur["index"])
            if cmd == "":
                # No comment, but the round is still recorded → coverage.
                collected[idx] = {"index": idx}
            else:
                collected[idx] = {"index": idx, "comment": text}
            k += 1
    except (KeyboardInterrupt, EOFError):
        echo("\n(interrupted)")

    if not collected:
        echo("(nothing marked)")
        return None

    # ≥90% round-coverage gate (mirrors the server). The natural flow — step
    # every round from 1 to the end — reaches 100%; an early :q can leave a
    # gap, so block & tell the user how many more rounds to walk.
    covered = len(collected)
    need = math.ceil(MARK_COVERAGE_THRESHOLD * last_index) if last_index else 0
    if covered < need:
        pct = round(100 * covered / last_index) if last_index else 0
        echo(
            f"coverage {pct}% ({covered}/{last_index} rounds) "
            f"< {round(MARK_COVERAGE_THRESHOLD * 100)}% — "
            f"walk {need - covered} more round(s) (comment or blank each) "
            "before submitting. Nothing submitted."
        )
        return None

    body = {
        "last_index": last_index,
        "description": description,
        "rounds": [collected[i] for i in sorted(collected)],
    }
    # ``post_fn`` (cli.session._post_marks) handles HTTP errors itself —
    # including a dedicated 409 "session advanced; re-enter" message — and
    # exits on failure, so it returns either a clean result dict or never.
    return post_fn(cfg, session_id, body, json_out)

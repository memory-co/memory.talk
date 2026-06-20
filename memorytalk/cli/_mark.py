"""``session mark`` helpers — submission loading, rendering, interactive flow.

Kept out of ``cli/session.py`` so the (chunky) interactive loop and YAML
parsing don't crowd the list/tag commands. See ``docs/cli/v4/session.md``.
"""
from __future__ import annotations

import sys

import click
import yaml

from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.config import Config
from memorytalk.util.ids import mark_seq


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


# ────────── interactive mode ──────────

def _round_text(r: dict) -> str:
    blocks = r.get("content") or []
    out = []
    for b in blocks:
        if isinstance(b, dict):
            t = b.get("text") or b.get("thinking")
            if t:
                out.append(str(t))
    return "\n".join(out).strip()


def _show_window(prev: dict | None, cur: dict) -> None:
    if prev is not None:
        click.echo(f"──────── round {prev['index']} ·(context)────────")
        click.echo(f"[{prev.get('role') or ''}] {_round_text(prev)}")
    click.echo(f"──────── round {cur['index']} ·(current · mark here)────────")
    click.echo(f"[{cur.get('role') or ''}] {_round_text(cur)}")


def run_interactive(cfg: Config, session_id: str, json_out: bool, post_fn) -> dict | None:
    """A 2-round sliding-window annotation loop (line-based — see Notes).

    Walks ``[r1,r2] → mark r2 → [r2,r3] → mark r3 → …``; the user types a
    mark for the *current* round (blank = skip, ``:back`` = step back,
    ``:q`` = quit). Marks are collected with monotonic ``m<n>`` ids and
    POSTed once at the end. Returns the submit response, or ``None`` if the
    user quit / marked nothing.

    ``last_index`` is locked once on entry (the session's round count when
    we start reading); if the session advanced meanwhile the server's
    optimistic lock rejects the batch at submit time.
    """
    # Pull the session's rounds via the read endpoint.
    try:
        read = api("POST", "/v4/read", cfg, json_body={"id": session_id})
    except ApiError as e:
        click.echo(f"error: {extract_error_message(e.payload)}", err=True)
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"error: cannot reach server: {e}", err=True)
        raise SystemExit(1)

    session = read.get("session") or {}
    rounds = session.get("rounds") or []
    if len(rounds) < 1:
        click.echo("error: session has no rounds to mark", err=True)
        raise SystemExit(1)

    last_index = len(rounds)   # rounds are 1-indexed → max idx == count
    click.echo(
        f"session {session_id} · {last_index} rounds · interactive mark "
        "(text+↵ = mark current / ↵ = skip / :back = back / :q = quit)"
    )
    description = click.prompt("description (scenario; blank ok)", default="", show_default=False)

    collected: list[dict] = []
    next_n = 1
    # Step k shows window [r_{k}, r_{k+1}] and marks r_{k+1}. Start at the
    # 2nd round (index 1); r1 is context-only.
    k = 1
    while k < len(rounds):
        prev = rounds[k - 1]
        cur = rounds[k]
        click.echo("")
        _show_window(prev, cur)
        text = click.prompt("mark>", default="", show_default=False)
        cmd = text.strip()
        if cmd == ":q":
            break
        if cmd == ":back":
            k = max(1, k - 1)
            continue
        if cmd == "":
            k += 1
            continue
        # A mark for the current round. The window's rounds are its natural
        # grounding indexes (prev..cur) — used only if the text has #…？.
        entry = {
            "id": mark_seq(next_n),
            "mark": text,
            "indexes": f"{prev['index']}-{cur['index']}",
        }
        collected.append(entry)
        next_n += 1
        k += 1

    if not collected:
        click.echo("(nothing marked)")
        return None

    body = {
        "last_index": last_index,
        "description": description,
        "marks": collected,
    }
    return post_fn(cfg, session_id, body, json_out)

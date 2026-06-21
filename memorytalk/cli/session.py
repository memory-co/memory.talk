"""CLI: memory.talk session {list, tag} — session maintenance.

Two subcommands:

  list  multi-filter listing (tag / source / endpoint / cwd / time)
  tag   query / set / unset kv tags on one session

Both call the HTTP API; the CLI is a thin translator. See
``docs/cli/v3/session.md`` for the user-facing contract.
"""
from __future__ import annotations
import datetime as _dt
import re
import sys

import click

from memorytalk.cli._format import (
    fmt_error, fmt_session_list, fmt_session_tag,
)
from memorytalk.cli._mark import (
    fmt_mark_result, load_submission, run_interactive,
)
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config
from memorytalk.util.tags import TagValidationError, parse_kv_args


_DURATION_RE = re.compile(r"^(\d+)([hdw])$")


def _duration_to_iso(value: str | None) -> str | None:
    """``7d`` / ``12h`` / ``2w`` → ISO timestamp ``N units`` ago.
    Bare ISO 8601 input is passed through after a parse sanity check.

    Returning the ISO string here (not relative semantics) lets the
    server treat ``since`` / ``until`` as opaque timestamps without
    needing its own clock-aware "duration" parser.
    """
    if not value:
        return None

    m = _DURATION_RE.match(value)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "h":
            delta = _dt.timedelta(hours=n)
        elif unit == "d":
            delta = _dt.timedelta(days=n)
        else:  # 'w'
            delta = _dt.timedelta(weeks=n)
        ts = _dt.datetime.now(_dt.UTC) - delta
        return ts.isoformat(timespec="seconds").replace("+00:00", "Z")

    # Treat as ISO 8601 — let the server enforce strictly. We only
    # do a coarse parse here to fail fast on obvious nonsense like
    # ``7days``, so the error blames the CLI input rather than the
    # generic 400 from the server.
    try:
        _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise click.BadParameter(
            f"invalid duration {value!r}, use '7d' / '12h' / '2w' or ISO date",
        )
    return value


@click.group("session")
def session() -> None:
    """Session maintenance: list / tag."""


# ────────── session list ──────────

@session.command("list")
@click.option("--source", type=str, default=None,
              help="Filter by adapter source (claude-code / codex / …)")
@click.option("--endpoint", type=str, default=None,
              help="Filter by <source>@<label>")
@click.option("--cwd", type=str, default=None,
              help="Filter by metadata.cwd prefix (absolute path)")
@click.option("--tag", "tags", multiple=True,
              help="K=V (equality) or K (presence); repeatable, AND")
@click.option("--since", "-d", "since", type=str, default=None,
              help="Lower bound on created_at: '7d' / '12h' / '2w' / ISO")
@click.option("--until", type=str, default=None,
              help="Upper bound on created_at: same syntax as --since")
@click.option("--limit", type=int, default=20, show_default=True,
              help="Max rows to return (1..200)")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def list_(
    source: str | None, endpoint: str | None, cwd: str | None,
    tags: tuple[str, ...], since: str | None, until: str | None,
    limit: int, json_out: bool,
) -> None:
    """List sessions by structural filters."""
    cfg = Config()

    try:
        since_iso = _duration_to_iso(since)
        until_iso = _duration_to_iso(until)
    except click.BadParameter as e:
        _emit_err(json_out, str(e))
        sys.exit(1)

    # Use a tuple list to preserve order + allow repeated ``tag`` params.
    params: list[tuple[str, str]] = []
    if source:
        params.append(("source", source))
    if endpoint:
        params.append(("endpoint", endpoint))
    if cwd:
        params.append(("cwd", cwd))
    for t in tags:
        params.append(("tag", t))
    if since_iso:
        params.append(("since", since_iso))
    if until_iso:
        params.append(("until", until_iso))
    params.append(("limit", str(limit)))

    try:
        result = api("GET", "/v4/sessions", cfg, params=params)
    except ApiError as e:
        _emit_err(json_out, extract_error_message(e.payload))
        sys.exit(1)
    except Exception as e:
        _emit_err(json_out, f"cannot reach server: {e}")
        sys.exit(1)

    # Echo the active filters so the rendered header has something
    # useful to show.
    filter_summary = _summarize_filters(
        source, endpoint, cwd, tags, since, until,
    )

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_session_list(result, filter_summary))


# ────────── session tag ──────────

@session.command("tag")
@click.argument("session_id")
@click.argument("kv_args", nargs=-1)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def tag(session_id: str, kv_args: tuple[str, ...], json_out: bool) -> None:
    """Query / set / unset kv tags on a session.

    No positional args after <session_id> → query current tags.
    """
    cfg = Config()

    try:
        set_, unset = parse_kv_args(kv_args)
    except TagValidationError as e:
        _emit_err(json_out, str(e))
        sys.exit(1)

    body = {"set": set_, "unset": unset}
    try:
        result = api(
            "PATCH", f"/v4/sessions/{session_id}/tags",
            cfg, json_body=body,
        )
    except ApiError as e:
        _emit_err(json_out, extract_error_message(e.payload))
        sys.exit(1)
    except Exception as e:
        _emit_err(json_out, f"cannot reach server: {e}")
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        # Query mode (no args) renders differently than set/unset —
        # ``fmt_session_tag`` switches on the third arg.
        is_query = not (set_ or unset)
        emit_md(fmt_session_tag(result, is_query=is_query))


# ────────── session mark ──────────

@session.command("mark")
@click.option("--session", "session_id", required=True,
              help="Session to annotate (sess_<...>)")
@click.option("--mark", "mark_file", type=str, default=None,
              help="Submission YAML path ('-' = stdin). Given → file mode; "
                   "omitted → interactive mode.")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def mark(session_id: str, mark_file: str | None, json_out: bool) -> None:
    """Annotate a session round-by-round ("以写代读"); #…？ auto-creates cards.

    --mark <file> (or '-' for stdin) → file mode (POST one submission).
    No --mark → interactive 2-round sliding-window mode.
    """
    cfg = Config()

    if mark_file is not None:
        # ── file / pipe mode ──
        try:
            body = load_submission(mark_file)
        except (click.BadParameter, ValueError) as e:
            _emit_err(json_out, str(e))
            sys.exit(1)
        result = _post_marks(cfg, session_id, body, json_out)
    else:
        # ── interactive mode ──
        result = run_interactive(cfg, session_id, json_out, _post_marks)
        if result is None:
            # nothing marked / user quit before submitting — clean exit
            return

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_mark_result(result))


# ────────── session clear-marks ──────────

@session.command("clear-marks")
@click.argument("session_id")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def clear_marks(session_id: str, json_out: bool) -> None:
    """Clear ALL marks for a session (marks/*.yaml + session_marks +
    card_sessions). Cards / positions / reviews / links are left untouched."""
    cfg = Config()
    try:
        result = api(
            "DELETE", f"/v4/sessions/{session_id}/marks", cfg,
        )
    except ApiError as e:
        _emit_err(json_out, extract_error_message(e.payload))
        sys.exit(1)
    except Exception as e:
        _emit_err(json_out, f"cannot reach server: {e}")
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        n = result.get("deleted_marks", 0)
        emit_md(f"cleared {n} mark(s) for {session_id}")


def _post_marks(cfg: Config, session_id: str, body: dict, json_out: bool) -> dict:
    """POST a submission to ``/v4/sessions/{sid}/marks``. Emits + exits on
    error (so callers get a clean ``dict`` or never return)."""
    try:
        return api(
            "POST", f"/v4/sessions/{session_id}/marks", cfg, json_body=body,
        )
    except ApiError as e:
        msg = extract_error_message(e.payload)
        if e.status_code == 409:
            # Optimistic lock: the session gained rounds since we read it.
            msg = f"{msg} — session advanced; re-read & re-mark."
        _emit_err(json_out, msg)
        raise SystemExit(1)
    except Exception as e:
        _emit_err(json_out, f"cannot reach server: {e}")
        raise SystemExit(1)


# ────────── helpers ──────────

def _emit_err(json_out: bool, msg: str) -> None:
    if json_out:
        emit_json_err(msg)
    else:
        emit_md_err(fmt_error(msg))


def _summarize_filters(
    source: str | None, endpoint: str | None, cwd: str | None,
    tags: tuple[str, ...], since: str | None, until: str | None,
) -> str:
    """Produce the ``filter: ...`` segment for the markdown header.
    Returns empty string when no filter is set."""
    parts: list[str] = []
    if source:
        parts.append(f"source={source}")
    if endpoint:
        parts.append(f"endpoint={endpoint}")
    if cwd:
        parts.append(f"cwd={cwd}")
    for t in tags:
        parts.append(f"tag={t}")
    if since:
        parts.append(f"since={since}")
    if until:
        parts.append(f"until={until}")
    return " · ".join(parts)

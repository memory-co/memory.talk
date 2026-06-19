"""CLI: ``memory.talk recall {hook,list,read}`` — v4 card recall.

Three subcommands, each a distinct concern:

  hook  — runtime: harness invokes this, stdin JSON or positional args.
          The CLI mints the canonical session_id client-side (via the
          adapter for ``--source``) and POSTs it to /v4/recall.
  list  — debug: show sessions that have recall history.
  read  — debug: show one session's recall timeline.

The hook MUST emit valid ``hookSpecificOutput`` JSON and exit 0 in every
branch — a non-zero exit blocks the user's prompt in the host CLI.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import click

from memorytalk.cli._format import fmt_error, fmt_recall_read, fmt_recall_sessions
from memorytalk.cli.card import _fmt_recall as fmt_recall
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.group("recall")
def recall() -> None:
    """Unconscious card recall — used at hook time by host AI CLIs, plus
    debug subcommands (list / read) for inspection."""


# ─────────────────── hook ───────────────────

@recall.command("hook")
@click.option("--source", required=True,
              help="Host adapter (e.g. claude-code, codex). REQUIRED — used "
                   "to mint the canonical session_id.")
@click.option("--location", default=None,
              help="Adapter location (filesystem path / URL). Defaults to "
                   "the adapter's DEFAULT_LOCATION.")
@click.argument("session_id", type=str, required=False, default=None)
@click.argument("prompt", type=str, required=False, default=None)
@click.option("--top-k", "top_k", type=int, default=None,
              help="Recall cap (default = server default)")
@click.option("--json", "json_out", is_flag=True, default=False,
              help="Emit JSON")
def hook_cmd(
    source: str,
    location: str | None,
    session_id: str | None,
    prompt: str | None,
    top_k: int | None,
    json_out: bool,
) -> None:
    """Hook entrypoint. Either stdin JSON (host plugins) or positional args."""
    payload = _read_stdin_payload()
    if payload is not None:
        _run_hook_stdin(source, location, top_k, payload)
        return

    if session_id is None or prompt is None:
        emit_md_err(fmt_error(
            "recall hook needs SESSION_ID and PROMPT (or stdin JSON)"
        ))
        sys.exit(2)

    _run_hook_positional(
        source, location, session_id, prompt, top_k, json_out,
    )


def _canonical_session_id(source: str, raw_session_id: str) -> str:
    """Mint the canonical ``sess-…`` id client-side from the adapter."""
    from memorytalk.adapters import get_adapter
    return get_adapter(source).mint_session_id(raw_session_id)


def _read_stdin_payload() -> dict | None:
    """Return the parsed JSON payload if stdin has one, else None."""
    if sys.stdin.isatty():
        return None
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _run_hook_stdin(
    source: str, location: str | None, top_k: int | None, payload: dict,
) -> None:
    """Stdin / plugin path. Always exits 0; emits hook JSON on stdout."""
    def _emit(ctx: str) -> None:
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": ctx,
            }
        }) + "\n")
        sys.stdout.flush()

    try:
        try:
            session_id = payload["session_id"]
            prompt = payload["prompt"]
            if not isinstance(session_id, str) or not isinstance(prompt, str):
                raise TypeError("session_id and prompt must be strings")
        except (KeyError, TypeError, ValueError) as e:
            sys.stderr.write(f"memory.talk hook: malformed stdin ({e})\n")
            _emit("")
            return

        # ── setup probe short-circuit ──
        from memorytalk.hooks.probe import PROBE_PREFIX, sentinel_path
        if prompt.startswith(PROBE_PREFIX):
            try:
                sentinel_path(prompt).write_text("ok\n", encoding="utf-8")
            except OSError:
                pass
            _emit("")
            return

        cfg = Config()

        # Suppress recall when the caller's cwd is the explore workspace.
        caller_cwd = payload.get("cwd")
        if caller_cwd and _same_path(caller_cwd, cfg.settings.explore.cwd):
            _emit("")
            return

        try:
            canonical = _canonical_session_id(source, session_id)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"memory.talk hook: session mint failed ({e})\n")
            _emit("")
            return

        body: dict = {"session_id": canonical, "prompt": prompt}
        if top_k is not None:
            body["top_k"] = top_k
        try:
            result = api("POST", "/v4/recall", cfg, json_body=body, timeout=2.0)
        except Exception as e:  # noqa: BLE001 — hook contract: never raise
            sys.stderr.write(f"memory.talk hook: recall failed ({e})\n")
            _emit("")
            return

        _emit(fmt_recall(result))
    except BaseException as e:  # noqa: BLE001
        sys.stderr.write(
            f"memory.talk hook: unexpected error ({type(e).__name__}: {e})\n"
        )
        try:
            _emit("")
        except Exception:
            pass


def _run_hook_positional(
    source: str, location: str | None,
    session_id: str, prompt: str, top_k: int | None, json_out: bool,
) -> None:
    """Manual CLI use. Errors get standard CLI treatment (md or json)."""
    cfg = Config()
    try:
        canonical = _canonical_session_id(source, session_id)
    except Exception as e:  # noqa: BLE001
        emit_md_err(fmt_error(f"cannot mint session id: {e}"))
        sys.exit(1)
    body: dict = {"session_id": canonical, "prompt": prompt}
    if top_k is not None:
        body["top_k"] = top_k
    try:
        result = api("POST", "/v4/recall", cfg, json_body=body)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)
    except Exception as e:
        if json_out:
            emit_json_err(str(e))
        else:
            emit_md_err(fmt_error(f"cannot reach server: {e}"))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        md = fmt_recall(result)
        if md:
            emit_md(md)


# ─────────────────── list ───────────────────

@recall.command("list")
@click.option("--limit", type=int, default=20,
              help="Max sessions to show (default: 20)")
@click.option("--json", "json_out", is_flag=True, default=False)
def list_cmd(limit: int, json_out: bool) -> None:
    """List sessions that have any recall history (most-recent first)."""
    cfg = Config()
    try:
        result = api("GET", f"/v4/recall/sessions?limit={limit}", cfg)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)
    except Exception as e:
        if json_out:
            emit_json_err(str(e))
        else:
            emit_md_err(fmt_error(f"cannot reach server: {e}"))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_recall_sessions(result))


# ─────────────────── read ───────────────────

@recall.command("read")
@click.argument("session_id", type=str)
@click.option("--limit", type=int, default=50,
              help="Max events to show (default: 50)")
@click.option("--reverse", is_flag=True, default=False,
              help="Newest first (default: oldest → newest)")
@click.option("--json", "json_out", is_flag=True, default=False)
def read_cmd(session_id: str, limit: int, reverse: bool, json_out: bool) -> None:
    """Show one session's recall timeline (prompt + returned + skipped)."""
    cfg = Config()
    path = (
        f"/v4/recall/sessions/{session_id}"
        f"?limit={limit}&reverse={'true' if reverse else 'false'}"
    )
    try:
        result = api("GET", path, cfg)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)
    except Exception as e:
        if json_out:
            emit_json_err(str(e))
        else:
            emit_md_err(fmt_error(f"cannot reach server: {e}"))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_recall_read(result))


# ─────────────────── helpers ───────────────────

def _same_path(a: str | Path, b: str | Path) -> bool:
    try:
        return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()
    except Exception:
        return False

"""CLI: recall <session_id> <prompt> [--top-k N] [--json].

Recall is the *hook-time* counterpart to ``search``: minimal output, no
audit trail, per-session dedup. The session_id can be raw or prefixed —
the server normalizes either way.

``--hook`` mode: read Claude Code's ``UserPromptSubmit`` JSON payload
from stdin, emit ``hookSpecificOutput`` JSON to stdout, **always exit
0**. A hook that errors out blocks the user's prompt — so any failure
funnels into an empty ``additionalContext`` and a clean return.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import click

from memorytalk.cli._format import fmt_error, fmt_recall
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.command("recall")
@click.argument("session_id", type=str, required=False, default=None)
@click.argument("prompt", type=str, required=False, default=None)
@click.option("--top-k", "top_k", type=int, default=None,
              help="Recall cap (default = settings.recall.default_top_k)")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
@click.option("--hook", "hook_mode", is_flag=True, default=False,
              help="Read Claude Code UserPromptSubmit payload from stdin; "
                   "emit hookSpecificOutput JSON. Always exits 0.")
def recall(session_id: str | None, prompt: str | None, top_k: int | None,
           json_out: bool, hook_mode: bool) -> None:
    """Hook-time recall: top-K cards relevant to this prompt (dedup per session)."""
    if hook_mode:
        _run_hook_mode(top_k)
        return

    if session_id is None or prompt is None:
        emit_md_err(fmt_error("recall requires SESSION_ID and PROMPT (or pass --hook)"))
        sys.exit(2)

    cfg = Config()
    body: dict = {"session_id": session_id, "prompt": prompt}
    if top_k is not None:
        body["top_k"] = top_k
    try:
        result = api("POST", "/v3/recall", cfg, json_body=body)
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


def _same_path(a: str | Path, b: str | Path) -> bool:
    """``~`` expansion + symlink resolution on both sides. Inlined here
    instead of restoring a util module — single caller, narrow contract."""
    try:
        return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()
    except Exception:
        return False


def _run_hook_mode(top_k: int | None) -> None:
    """UserPromptSubmit hook entry. Always exits 0; emits hook JSON on stdout.

    Errors funnel through ``_emit("")`` so Claude never sees a non-zero
    exit or malformed stdout. The body is wrapped in an outer
    ``BaseException`` net as belt-and-braces — if anything unforeseen
    raises (Config() against corrupt settings.json, an OS error, a bug
    here), we still emit valid hook JSON and return cleanly.
    """
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
            payload = json.loads(sys.stdin.read())
            session_id = payload["session_id"]
            prompt = payload["prompt"]
            if not isinstance(session_id, str) or not isinstance(prompt, str):
                raise TypeError("session_id and prompt must be strings")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            sys.stderr.write(f"memory.talk hook: malformed stdin ({e})\n")
            _emit("")
            return

        cfg = Config()

        # Suppress recall when the caller's cwd is the explore workspace.
        # explore is a "look at memory deliberately" mode, not a "memory
        # autocompletes my work" mode — auto-injecting context defeats
        # the point. Best-effort: if the cwd lookup fails for any reason
        # we fall through to normal recall (the broader hook contract is
        # "never block the user prompt", not "always suppress").
        caller_cwd = payload.get("cwd")
        if caller_cwd and _same_path(caller_cwd, cfg.settings.explore.cwd):
            _emit("")
            return

        body: dict = {"session_id": session_id, "prompt": prompt}
        if top_k is not None:
            body["top_k"] = top_k
        try:
            # Short timeout — server may be down; we must not hang the
            # hook. 2s matches the v2 contract.
            result = api("POST", "/v3/recall", cfg, json_body=body, timeout=2.0)
        except Exception as e:  # noqa: BLE001
            # DO NOT narrow this. Hook contract: any exception MUST
            # funnel to _emit("") + return (exit 0). Narrowing risks a
            # future exception type (OSError, ssl errors, malformed
            # response KeyError) escaping and breaking the hook
            # silently — every user prompt would get blocked.
            sys.stderr.write(f"memory.talk hook: recall failed ({e})\n")
            _emit("")
            return

        # fmt_recall returns "" on empty, matching the empty-context contract.
        _emit(fmt_recall(result))
    except BaseException as e:  # noqa: BLE001
        # Outer net — covers Config() failures, OS errors, anything the
        # inner blocks didn't anticipate. The hook MUST emit valid JSON
        # and return 0 even when something completely unexpected blows up.
        sys.stderr.write(f"memory.talk hook: unexpected error "
                         f"({type(e).__name__}: {e})\n")
        try:
            _emit("")
        except Exception:
            pass

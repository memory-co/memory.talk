"""CLI: recall <session_id> <prompt> [--top-k N] [--json] → POST /v2/recall.

--hook mode: read Claude Code UserPromptSubmit JSON payload from stdin,
emit Claude hookSpecificOutput JSON to stdout, exit 0 on every error
(must never block the user prompt).
"""
from __future__ import annotations
import json
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_recall
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.command("recall")
@click.argument("session_id", required=False, default=None)
@click.argument("prompt", required=False, default=None)
@click.option("--top-k", type=int, default=None, help="Top-k (default from settings.recall)")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
@click.option("--hook", "hook_mode", is_flag=True, default=False,
              help="Read Claude Code UserPromptSubmit payload from stdin; "
                   "emit Claude hookSpecificOutput JSON. Always exits 0.")
def recall(session_id: str | None, prompt: str | None, top_k: int | None,
           data_root: str | None, json_out: bool, hook_mode: bool) -> None:
    """Hook-stage memory recall: top-K cards inlined for the AI context."""
    if hook_mode:
        _run_hook_mode(top_k, data_root)
        return

    # CLI mode — args required
    if session_id is None or prompt is None:
        emit_md_err(fmt_error("recall requires SESSION_ID and PROMPT (or pass --hook)"))
        sys.exit(2)

    cfg = Config(data_root) if data_root else Config()
    body = {"session_id": session_id, "query": prompt}
    if top_k is not None:
        body["top_k"] = top_k
    try:
        result = api("POST", "/v2/recall", cfg, json_body=body, timeout=30.0)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_recall(result))


def _run_hook_mode(top_k: int | None, data_root: str | None) -> None:
    """UserPromptSubmit hook entry. Always exits 0; emits hook JSON on stdout.

    Errors funnel through _emit("") so Claude never sees a non-zero exit
    or a malformed stdout. The body is wrapped in an outer
    BaseException net as a belt-and-braces guarantee — if anything
    unforeseen raises (e.g. Config() against a corrupt settings.json,
    a bug in this function, an OS-level error not caught below), we
    still emit a valid hook JSON and return cleanly.
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
        # Parse stdin
        try:
            raw = sys.stdin.read()
            payload = json.loads(raw)
            session_id = payload["session_id"]
            prompt = payload["prompt"]
            if not isinstance(session_id, str) or not isinstance(prompt, str):
                raise TypeError("session_id and prompt must be strings")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            sys.stderr.write(f"memory-talk hook: malformed stdin ({e})\n")
            _emit("")
            return

        # Call recall API with short timeout (server may be down — fail fast)
        cfg = Config(data_root) if data_root else Config()
        body: dict = {"session_id": session_id, "query": prompt}
        if top_k is not None:
            body["top_k"] = top_k
        try:
            result = api("POST", "/v2/recall", cfg, json_body=body, timeout=2.0)
        except Exception as e:  # noqa: BLE001
            # DO NOT narrow this. Hook contract: any exception here MUST funnel
            # to _emit("") + return (exit 0). Narrowing risks a future exception
            # type (OSError, KeyError on malformed response, ssl errors, ...)
            # escaping and breaking the UserPromptSubmit hook silently.
            sys.stderr.write(f"memory-talk hook: recall failed ({e})\n")
            _emit("")
            return

        # Format response — reuse the same fmt_recall used by the human-
        # facing CLI mode, so Claude sees the bash-block "memory-talk view
        # <card>  # <summary>" shape (concise, single-line summaries,
        # cards as runnable commands). fmt_recall returns "" on empty
        # hits, matching our empty-additionalContext contract.
        _emit(fmt_recall(result))
    except BaseException as e:  # noqa: BLE001
        # Outer net — covers Config() failures, OS errors, anything the
        # inner blocks didn't anticipate. The hook MUST emit valid JSON
        # and return 0 even when something completely unexpected blows up.
        sys.stderr.write(f"memory-talk hook: unexpected error ({type(e).__name__}: {e})\n")
        try:
            _emit("")
        except Exception:
            pass

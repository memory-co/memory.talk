"""CLI: recall <session_id> <prompt> [--top-k N] [--json].

Recall is the *hook-time* counterpart to ``search``: minimal output, no
audit trail, per-session dedup. The session_id can be raw or prefixed —
the server normalizes either way.
"""
from __future__ import annotations
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_recall
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.command("recall")
@click.argument("session_id", type=str)
@click.argument("prompt", type=str)
@click.option("--top-k", "top_k", type=int, default=None,
              help="Recall cap (default = settings.recall.default_top_k)")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def recall(session_id: str, prompt: str, top_k: int | None, json_out: bool) -> None:
    """Hook-time recall: top-K cards relevant to this prompt (dedup per session)."""
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
        # Empty recall → no Markdown output (per docs: harness reads empty
        # stdout as "nothing to inject").
        md = fmt_recall(result)
        if md:
            emit_md(md)

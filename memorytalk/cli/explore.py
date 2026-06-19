"""CLI: memory.talk explore {create, view, list}.

A prior/posterior card-extraction workspace (see docs/works/v3/explore.md).
Thin HTTP client over /v3/explores. Card/review minting under an explore
goes through ``card create`` / ``review create`` with an explore_id.
"""
from __future__ import annotations

import sys

import click

from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.group("explore")
def explore() -> None:
    """Prior/posterior card-extraction workspace: create / view / list."""


def _call(method: str, path: str, json_out: bool, **kw):
    cfg = Config()
    try:
        return api(method, path, cfg, **kw)
    except ApiError as e:
        (emit_json_err if json_out else
         (lambda p: emit_md_err(extract_error_message(p))))(e.payload)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 — connection / unexpected
        (emit_json_err if json_out else emit_md_err)(
            {"error": str(e)} if json_out else f"cannot reach server: {e}")
        sys.exit(1)


@explore.command("create")
@click.argument("entrypoint_session_id", required=False)
@click.option("--at", "divider_at", default=None,
              help="Divider time (ISO, UTC) — use instead of an entrypoint session")
@click.option("--note", default=None, help="Free-text note")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def create(entrypoint_session_id, divider_at, note, json_out) -> None:
    """Create an explore: pass an entrypoint session id, or --at <time>."""
    if not entrypoint_session_id and not divider_at:
        emit_md_err("give an entrypoint session id or --at <time>")
        sys.exit(1)
    result = _call("POST", "/v4/explores", json_out, json_body={
        "entrypoint_session_id": entrypoint_session_id,
        "divider_at": divider_at, "note": note,
    })
    if json_out:
        emit_json(result)
    else:
        emit_md(
            f"explore `{result['explore_id']}` · divider {result['divider_at']}\n"
            f"prior {result['prior_count']} · posterior {result['posterior_count']}\n"
            f"workspace: {result['dir_path']}"
        )


@explore.command("view")
@click.argument("explore_id")
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def view(explore_id, json_out) -> None:
    """Show an explore's prior/posterior split."""
    result = _call("GET", f"/v4/explores/{explore_id}", json_out)
    if json_out:
        emit_json(result)
    else:
        prior = result.get("prior", [])
        posterior = result.get("posterior", [])
        lines = [
            f"explore `{result['explore_id']}` · divider {result['divider_at']}",
            f"\n先验 prior ({len(prior)}):",
            *[f"  {s['session_id']}  {s.get('last_round_update_time','')}" for s in prior],
            f"\n后验 posterior ({len(posterior)}):",
            *[f"  {s['session_id']}  {s.get('last_round_update_time','')}" for s in posterior],
        ]
        emit_md("\n".join(lines))


@explore.command("list")
@click.option("--limit", type=int, default=50, show_default=True)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON")
def list_(limit, json_out) -> None:
    """List explores, newest first."""
    result = _call("GET", "/v4/explores", json_out, params={"limit": limit})
    if json_out:
        emit_json(result)
    else:
        rows = result.get("explores", [])
        emit_md("\n".join(
            f"`{r['explore_id']}`  divider {r['divider_at']}  {r.get('note') or ''}"
            for r in rows
        ) or "(no explores)")

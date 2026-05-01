"""Markdown summary table emitted on stdout at the end of the wizard.

Pure formatting — takes the wizard's result dict + the (re-loaded)
Config and produces the final Markdown the user sees.
"""
from __future__ import annotations
from pathlib import Path

from memorytalk.config import Config

def _humanize_paths(paths: list[str]) -> str:
    """For the wizard summary: '4 fields (a.b, c, d.e, f)'."""
    if not paths:
        return "nothing"
    return f"{len(paths)} field" + ("s" if len(paths) != 1 else "") + " (" + ", ".join(paths) + ")"


def _summary_md(cfg: Config, result: dict, *, memory_talk_bin: Path) -> str:
    rows: list[tuple[str, str]] = []
    rows.append(("data_root", f"`{cfg.data_root}`"))
    rows.append(("settings", f"`{cfg.settings_path}`"))
    rows.append(("env", f"`{memory_talk_bin.parent.parent}`"))

    s = cfg.settings
    rows.append(("embedding", _embedding_label(s.embedding)))
    rows.append(("vector", s.vector.provider))
    rows.append(("relation", s.relation.provider))
    rows.append(("port", str(s.server.port)))

    server = result.get("server")
    rows.append(("server", _server_label(server)))

    takeover = result.get("path_takeover") or {}
    rows.append(("PATH takeover", _takeover_label(takeover)))

    rows.append(("changed", _changed_label(result)))

    out = ["# setup · **ok**", "", "| field | value |", "|---|---|"]
    for k, v in rows:
        out.append(f"| {k} | {v} |")
    out.append("")
    return "\n".join(out)


def _embedding_label(emb) -> str:
    if emb.provider == "openai":
        return f"openai · {emb.model} · dim {emb.dim}"
    if emb.provider == "local":
        return f"local · {emb.model} · dim {emb.dim}"
    return f"{emb.provider} · dim {emb.dim}"


def _server_label(payload: dict | None) -> str:
    if payload is None:
        return "unchanged"
    status = payload.get("status", "?")
    if status == "started":
        suffix = " · restarted" if payload.get("restarted") else ""
        return f"started · pid {payload.get('pid')}{suffix}"
    if status == "running":
        return f"running · pid {payload.get('pid')} (no change)"
    if status == "running_stale":
        return f"running · pid {payload.get('pid')} (stale — needs restart)"
    if status == "already_running":
        return f"already_running · pid {payload.get('pid')}"
    if status == "not_started":
        return "not_started · run `memory-talk server start` to launch"
    if status == "failed":
        return f"failed (exit {payload.get('exit_code')}) — see stderr"
    return status


def _takeover_label(takeover: dict) -> str:
    actions = takeover.get("actions") or []
    if not actions:
        return "unchanged"
    counts: dict[str, int] = {}
    for a in actions:
        s = a.get("status", "?")
        counts[s] = counts.get(s, 0) + 1
    bits: list[str] = []
    if counts.get("ok"):
        bits.append(f"{counts['ok']} already correct")
    if counts.get("redirected"):
        bits.append(f"{counts['redirected']} symlink redirected")
    if counts.get("replaced"):
        bits.append(f"{counts['replaced']} file replaced (.bak created)")
    if counts.get("skipped"):
        bits.append(f"{counts['skipped']} skipped (declined)")
    if counts.get("no_perm"):
        bits.append(f"{counts['no_perm']} no permission")
    if counts.get("not_found"):
        bits.append("none on $PATH — add target dir to PATH manually")
    if counts.get("windows"):
        bits.append("windows — skipped")
    return ", ".join(bits) if bits else "nothing to do"


def _changed_label(result: dict) -> str:
    if result.get("first_install"):
        bits = ["settings.json (created)", "dirs"]
        server = result.get("server") or {}
        if server.get("status") == "started":
            bits.append("server started")
        return ", ".join(bits)
    if not result.get("wrote_settings"):
        return "nothing — config unchanged"
    bits = []
    fields = result.get("settings_changed") or []
    if fields:
        bits.append(_humanize_paths(fields))
    server = result.get("server") or {}
    if server.get("restarted"):
        bits.append("server restarted")
    return ", ".join(bits) if bits else "nothing"

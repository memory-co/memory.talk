"""Markdown summary table emitted on stdout at the end of the wizard.

Pure formatting — takes the wizard's result dict + the (re-loaded)
Config and produces the final Markdown the user sees.
"""
from __future__ import annotations
from pathlib import Path

from memorytalk.config import Config

from .helpers import humanize_paths


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

    alias = result.get("alias") or {}
    rows.append(("alias", _alias_label(alias)))

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


def _alias_label(alias: dict) -> str:
    status = alias.get("status", "")
    link = alias.get("link_path", "")
    target = alias.get("target", "")
    if status == "created":
        return f"`{link} → {Path(target).name}`"
    if status == "noop":
        return f"`{link}` (already points to `{Path(target).name}`)"
    if status == "overwrote":
        return f"`{link} → {Path(target).name}` (replaced)"
    if status == "skipped_other_target":
        return f"skipped — {link} points elsewhere"
    if status == "skipped_no_perm":
        return f"skipped (no write permission) — run manually: `ln -s {target} {link}`"
    if status == "skipped_regular_file":
        return f"skipped — `{link}` is a regular file"
    if status == "skipped_windows":
        return "skipped (windows — use a .bat or PowerShell alias instead)"
    if status == "skipped_not_found":
        return f"skipped — {alias.get('message', 'memory-talk not on PATH')}"
    return status


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
        bits.append(humanize_paths(fields))
    server = result.get("server") or {}
    if server.get("restarted"):
        bits.append("server restarted")
    return ", ".join(bits) if bits else "nothing"

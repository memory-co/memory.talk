"""Wizard orchestrator — composes the per-step modules into one flow.

The flow:
  1. embedding (always asked)
  2. vector + relation provider (single-option in v1 but surfaced)
  3. server port
  4. carry over untouched sections (ttl/search/recall)
  5. diff vs old settings — short-circuit if nothing changed
  6. probe the embedding provider if it (or first install) changed
  7. atomic write + ensure_dirs
  8. server start/restart
  9. memory.talk symlink
"""
from __future__ import annotations
from pathlib import Path

from memorytalk.config import Config, Settings

from . import _prompt
from ._io import err_console
from .helpers import diff_settings, write_settings_atomic
from .steps.alias import _step_alias
from .steps.embedding import _step_embedding, _step_probe_embedding
from .steps.provider import _step_choice
from .steps.server import _step_server


def _wizard(
    cfg: Config,
    old_raw: dict | None,
    is_first_install: bool,
    *,
    memory_talk_bin: Path,
) -> dict:
    is_first_install_str = "首次安装" if is_first_install else "已有配置 — 修改模式"
    err_console.print(f"[bold]memory-talk setup[/bold] · {is_first_install_str}")
    err_console.print(f"data_root: [cyan]{cfg.data_root}[/cyan]")
    err_console.print(f"env:       [cyan]{memory_talk_bin.parent.parent}[/cyan]\n")

    base = dict(old_raw) if old_raw else Settings().model_dump()

    # 1. embedding provider
    new_settings = _step_embedding(base)

    # 2. vector / relation (single-option but exposed)
    new_settings["vector"] = {"provider": _step_choice(
        "vector provider", ["lancedb"], (base.get("vector") or {}).get("provider", "lancedb"),
    )}
    new_settings["relation"] = {"provider": _step_choice(
        "relation provider", ["sqlite"], (base.get("relation") or {}).get("provider", "sqlite"),
    )}

    # 3. server port
    server_block = base.get("server") or {}
    port_str = _prompt.text(
        "server port",
        default=str(int(server_block.get("port", 7788))),
        validate=lambda v: (v.strip().isdigit() and 1 <= int(v) <= 65535)
        or "must be an integer in 1..65535",
    )
    new_settings["server"] = {"port": int(port_str)}

    # Carry over other sections (ttl / search / recall) untouched.
    for key in ("ttl", "search", "recall"):
        if key in base:
            new_settings[key] = base[key]

    # 4. diff
    changed = diff_settings(old_raw or {}, new_settings) if old_raw else ["(initial)"]

    if old_raw is not None and not changed:
        err_console.print("\n[dim]config unchanged — nothing to write[/dim]")
        return {
            "settings_changed": [],
            "wrote_settings": False,
            "ensured_dirs": False,
            "server": None,
            "alias": None,
            "first_install": False,
        }

    # 5. embedding probe (only if embedding section actually differs OR first install)
    embedding_changed = old_raw is None or new_settings.get("embedding") != (old_raw.get("embedding") or {})
    if embedding_changed:
        _step_probe_embedding(cfg, new_settings)

    # 6. write + ensure_dirs
    write_settings_atomic(cfg.settings_path, new_settings)
    cfg._settings = None  # type: ignore[attr-defined]
    cfg.ensure_dirs()

    # 7. server start/restart prompt
    server_payload = _step_server(cfg, old_raw is not None and bool(changed))

    # 8. symlink (alongside whichever memory-talk we're currently running)
    alias_result = _step_alias(memory_talk_bin)

    return {
        "settings_changed": changed,
        "wrote_settings": True,
        "ensured_dirs": True,
        "server": server_payload,
        "alias": alias_result,
        "first_install": is_first_install,
    }

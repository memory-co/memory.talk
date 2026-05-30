"""Per-host install state cache. NOT a source of truth — only used to
display ``last verified Xm ago`` and to short-circuit re-materialize
when the wheel's plugin bundle hash matches what's on disk.

All "is the plugin installed?" decisions come from the host CLI itself
(``claude plugin list``, ``codex plugin list``); this file is just a hint."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _path(data_root: Path) -> Path:
    return data_root / "hook_state.json"


def load(data_root: Path) -> dict:
    p = _path(data_root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data_root: Path, data: dict) -> None:
    p = _path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(p)


def record_verified(data_root: Path, host_name: str, plugin_hash: str) -> None:
    data = load(data_root)
    data[host_name] = {
        "last_verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plugin_dir_hash": plugin_hash,
    }
    save(data_root, data)


def clear(data_root: Path, host_name: str) -> None:
    data = load(data_root)
    if host_name in data:
        del data[host_name]
        save(data_root, data)


def last_verified(data_root: Path, host_name: str) -> str | None:
    return load(data_root).get(host_name, {}).get("last_verified_at")

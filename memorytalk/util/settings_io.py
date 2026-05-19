"""Generic JSON dict I/O + diff used by the setup wizard.

Three helpers, no domain knowledge — every function treats the file as
"an arbitrary JSON dict" and never asserts anything about the settings
schema. Reusable by any CLI that wants atomic-write JSON or recursive
dict diff.
"""
from __future__ import annotations
import json
import os
from pathlib import Path


def read_settings_raw(path: Path) -> dict | None:
    """Return the raw JSON content of ``path``, or None if missing/empty.

    None means "no existing config" — used by setup to choose between
    first-install and reconfigure paths. A corrupt file raises
    ``ValueError`` (caller decides whether to back it up + re-init).
    """
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return None
    return json.loads(text)


def write_settings_atomic(path: Path, data: dict) -> None:
    """Write ``data`` to ``path`` as pretty JSON via tmp + atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def diff_settings(old: dict, new: dict, prefix: str = "") -> list[str]:
    """Dotted-path list of fields that differ. Recurses into nested dicts."""
    paths: list[str] = []
    for key in sorted(set(old) | set(new)):
        ov = old.get(key, _MISSING)
        nv = new.get(key, _MISSING)
        path = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(ov, dict) and isinstance(nv, dict):
            paths.extend(diff_settings(ov, nv, path))
        elif ov != nv:
            paths.append(path)
    return paths


_MISSING = object()

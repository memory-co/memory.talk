"""Helpers for `memory-talk setup`.

Pure functions:
- read_settings_raw: load settings.json without going through Config defaults
- write_settings_atomic: tmp + rename
- diff_settings: list dotted paths that changed between two dicts
- create_symlink: idempotent symlink with classified result
- detect_install_mode: figure out whether the running memory-talk lives
  inside <data_root>/.venv/

These avoid pulling in click/rich so they're easy to unit-test.
"""
from __future__ import annotations
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


# ---------- settings.json ----------

def read_settings_raw(path: Path) -> dict | None:
    """Return the raw JSON content of settings.json, or None if missing.

    None means "no existing config" — used by setup to decide between
    first-install and reconfigure paths. A corrupt file raises ValueError
    (caller decides whether to back it up + re-init).
    """
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return None
    return json.loads(text)


def write_settings_atomic(path: Path, data: dict) -> None:
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


# ---------- symlink ----------

@dataclass
class SymlinkResult:
    status: str  # created | noop | overwrote | skipped_other_target | skipped_no_perm | skipped_windows | skipped_regular_file
    link_path: Path
    target: Path
    message: str = ""


def create_symlink(target: Path, link_path: Path, *, overwrite: bool = False) -> SymlinkResult:
    """Idempotent symlink. Refuses to clobber a regular (non-symlink) file.

    Behavior:
    - link_path doesn't exist          → create, return "created"
    - link_path is a symlink to target → no-op, return "noop"
    - link_path is a symlink to else   → if overwrite=True, replace; else "skipped_other_target"
    - link_path is a regular file      → never touch, return "skipped_regular_file"
    - PermissionError on write         → "skipped_no_perm"
    - Windows                          → "skipped_windows" (requires admin)
    """
    if sys.platform == "win32":
        return SymlinkResult(
            status="skipped_windows", link_path=link_path, target=target,
            message="Windows symlinks require admin / dev mode; skipped",
        )

    if link_path.is_symlink():
        try:
            existing = Path(os.readlink(link_path))
        except OSError:
            existing = None
        if existing == target:
            return SymlinkResult(status="noop", link_path=link_path, target=target)
        if not overwrite:
            return SymlinkResult(
                status="skipped_other_target", link_path=link_path, target=target,
                message=f"link points to {existing}, not the requested target",
            )
        try:
            link_path.unlink()
        except PermissionError as e:
            return SymlinkResult(
                status="skipped_no_perm", link_path=link_path, target=target,
                message=str(e),
            )

    if link_path.exists() and not link_path.is_symlink():
        return SymlinkResult(
            status="skipped_regular_file", link_path=link_path, target=target,
            message="a regular file with this name exists; not overwriting",
        )

    try:
        os.symlink(target, link_path)
    except PermissionError as e:
        return SymlinkResult(
            status="skipped_no_perm", link_path=link_path, target=target,
            message=str(e),
        )
    return SymlinkResult(
        status="overwrote" if overwrite else "created",
        link_path=link_path, target=target,
    )


# ---------- install mode ----------

def detect_install_mode(data_root: Path) -> str:
    """Return 'standard' if shutil.which('memory-talk') resolves into the
    venv at <data_root>/.venv/bin/memory-talk; otherwise 'current'.

    'current' is the default — it covers system Python, --user installs,
    arbitrary venvs, etc. 'standard' is only declared when the running
    binary is unambiguously the venv we'd create.
    """
    found = shutil.which("memory-talk")
    if not found:
        return "current"
    expected = data_root / ".venv" / "bin" / "memory-talk"
    try:
        return "standard" if Path(found).resolve() == expected.resolve() else "current"
    except OSError:
        return "current"


# ---------- summary helpers ----------

def humanize_paths(paths: Iterable[str]) -> str:
    """For the wizard summary: '4 fields (a.b, c, d.e, f)'."""
    paths = list(paths)
    if not paths:
        return "nothing"
    return f"{len(paths)} field" + ("s" if len(paths) != 1 else "") + " (" + ", ".join(paths) + ")"

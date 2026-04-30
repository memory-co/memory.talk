"""Pure helpers for the setup wizard.

Read/write/diff settings and the idempotent symlink primitive. No click,
no rich, no networking — easy to unit-test, no side effects beyond the
filesystem operation each function explicitly does.
"""
from __future__ import annotations
import json
import os
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
    """Idempotent symlink. Refuses to clobber a regular (non-symlink) file."""
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


# ---------- summary helpers ----------

def humanize_paths(paths: Iterable[str]) -> str:
    """For the wizard summary: '4 fields (a.b, c, d.e, f)'."""
    paths = list(paths)
    if not paths:
        return "nothing"
    return f"{len(paths)} field" + ("s" if len(paths) != 1 else "") + " (" + ", ".join(paths) + ")"

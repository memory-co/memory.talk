"""Copy wheel-bundled plugin assets into a real filesystem dir so host
CLIs can register them as a local marketplace."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import memorytalk


def assets_root() -> Path:
    """Real filesystem path of the wheel-bundled plugin assets.
    Works for editable installs and standard wheel installs (where the
    package-data ends up alongside the .py modules in site-packages)."""
    return Path(memorytalk.__file__).parent / "_hook_assets"


def host_asset_dir(host_subdir: str) -> Path:
    """Source dir for one host's marketplace (inside the wheel)."""
    return assets_root() / host_subdir


def materialized_dir(data_root: Path, host_subdir: str) -> Path:
    """Destination dir on the user's disk."""
    return data_root / "hook_plugins" / host_subdir


def dir_hash(d: Path) -> str:
    """Stable sha256 of all .json files under ``d``. Order-independent."""
    if not d.exists():
        return ""
    h = hashlib.sha256()
    for p in sorted(d.rglob("*.json")):
        rel = p.relative_to(d).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def materialize(host_subdir: str, dst: Path) -> bool:
    """Copy wheel-bundled assets to ``dst``. Returns True if any change
    was written (allows callers to skip re-registration when no drift)."""
    src = host_asset_dir(host_subdir)
    if not src.exists():
        raise FileNotFoundError(f"bundled assets missing: {src}")
    if dir_hash(src) == dir_hash(dst):
        return False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True


def bundled_hash(host_subdir: str) -> str:
    return dir_hash(host_asset_dir(host_subdir))

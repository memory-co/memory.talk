"""Storage abstraction — primitives only, no domain knowledge.

Swapping local-fs for S3 (or another backend) should not require touching
domain code. Domain operations like "write a session's meta.json" live
in ``repository/<kind>.py`` and call into Storage with full keys.

Primitives:
- ``write_text(key, content)``  — atomic put
- ``read_text(key)``            — get; None if missing
- ``append_text(key, content)`` — append-only (caller pre-formats lines)
- ``exists(key)``               — head
- ``delete(key)``               — best-effort; missing is OK
- ``delete_prefix(prefix)``     — recursive rmtree; missing prefix is OK
- ``list_subkeys(prefix)``      — recursive list of file keys under prefix

Keys are forward-slash strings rooted at the data root, e.g.
``sessions/claude-code/la/sess_lancedb/meta.json``.
"""
from __future__ import annotations
from pathlib import Path
from typing import Protocol

import aiofiles
import aiofiles.os


class Storage(Protocol):
    async def write_text(self, key: str, content: str) -> None: ...
    async def read_text(self, key: str) -> str | None: ...
    async def append_text(self, key: str, content: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def delete(self, key: str) -> None: ...
    async def delete_prefix(self, prefix: str) -> None: ...
    async def list_subkeys(self, prefix: str) -> list[str]: ...


class LocalStorage:
    """Local-filesystem implementation of Storage.

    Atomic writes go via tmp + rename. Appends use O_APPEND. List scans
    the prefix subtree and returns sorted relative file keys.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key

    async def write_text(self, key: str, content: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(content)
        await aiofiles.os.replace(str(tmp), str(p))

    async def read_text(self, key: str) -> str | None:
        p = self._path(key)
        if not p.exists():
            return None
        async with aiofiles.open(p, "r", encoding="utf-8") as f:
            return await f.read()

    async def append_text(self, key: str, content: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(p, "a", encoding="utf-8") as f:
            await f.write(content)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def delete(self, key: str) -> None:
        p = self._path(key)
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    async def delete_prefix(self, prefix: str) -> None:
        """Recursively remove the directory at ``prefix``. Missing prefix
        is OK (no-op). Synchronous ``shutil.rmtree`` is fine here — the
        IO is one syscall per inode, no fan-out worth offloading."""
        import shutil
        p = self._path(prefix)
        if not p.exists():
            return
        if p.is_file():
            # Defensive — caller probably meant ``delete`` for a single
            # file; do the obvious thing rather than refuse.
            p.unlink()
            return
        shutil.rmtree(p)

    async def list_subkeys(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        out: list[str] = []
        for f in sorted(base.rglob("*")):
            if f.is_file():
                out.append(str(f.relative_to(self.root)).replace("\\", "/"))
        return out

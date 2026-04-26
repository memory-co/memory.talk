"""Storage abstraction — primitives only, no domain knowledge.

The point of this layer is so that swapping local-fs for S3 (or any other
backend) doesn't require touching domain code. Domain operations like
"write a session's meta.json" live in `repository/<kind>.py` and call
into Storage with full keys.

Storage primitives:
- ``write_text(key, content)``  atomic put
- ``read_text(key)``            get; None if missing
- ``append_text(key, content)`` append-only — caller pre-formats lines
- ``exists(key)``               head
- ``delete(key)``               best-effort; missing is OK
- ``list_subkeys(prefix)``      recursive list of file keys under prefix

Keys are forward-slash strings rooted at the data root, e.g.
"sessions/claude-code/la/sess_lancedb/meta.json". The local impl maps
them onto disk; an S3 impl would use them as object keys directly.
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
    async def list_subkeys(self, prefix: str) -> list[str]: ...


class LocalStorage:
    """Local-filesystem implementation of Storage.

    Atomic writes go via temp + rename. Appends use O_APPEND. List scans
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

    async def list_subkeys(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        out: list[str] = []
        for f in sorted(base.rglob("*")):
            if f.is_file():
                out.append(str(f.relative_to(self.root)).replace("\\", "/"))
        return out

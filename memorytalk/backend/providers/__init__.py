"""存储介质的两族基类(docs/designs/v5/provider.md):文件系统型、数据库型。只有介质原语,没有业务。"""
from __future__ import annotations

import os
from pathlib import Path

from .db import Column, DatabaseProvider, SQLite, Table
from .fs import FileSystemProvider, LocalFS


def load_store(home: Path) -> FileSystemProvider | DatabaseProvider:
    """MEMORY_TALK_STORE=fs(默认)| sqlite。行为不来自文件。"""
    kind = os.environ.get("MEMORY_TALK_STORE", "fs")
    if kind == "fs":
        return LocalFS(home)
    if kind == "sqlite":
        return SQLite(Path(os.environ.get("MEMORY_TALK_SQLITE", str(home / "memory.sqlite"))))
    raise RuntimeError(f"MEMORY_TALK_STORE={kind!r} 不认识(有:fs / sqlite)")


__all__ = ["FileSystemProvider", "LocalFS", "DatabaseProvider", "SQLite", "Column", "Table", "load_store"]

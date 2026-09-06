"""读各平台的会话记录 → Round。agent server 把手的「读 round」那一半。"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from models.task import Round


class TranscriptAdapter(Protocol):
    name: str

    def find(self, cwd: Path, since_mtime: float) -> Path | None:
        """在这个 cwd 下、会话创建之后新出现的那份记录。找不到 → None(不撒谎)。"""

    def rounds(self, path: Path) -> list[Round]: ...

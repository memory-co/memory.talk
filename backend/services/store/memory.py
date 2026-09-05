"""memory/ 仓库:git 封装 + 布局,认知层的 canonical(store.md)。"""
from __future__ import annotations

from pathlib import Path

from .git import GitRepo
from .paths import MemoryLayout


class Memory:
    def __init__(self, root: Path, author_name: str, author_email: str) -> None:
        self.layout = MemoryLayout(root)
        self.git = GitRepo(root, author_name, author_email)
        self.git.ensure()

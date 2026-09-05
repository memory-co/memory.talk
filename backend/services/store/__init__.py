"""StoreService:持有 memory 仓库(git)和 tasks 根(裸文件)。其余 service 的依赖。"""
from __future__ import annotations

from config import Config

from .files import atomic_write, read_text
from .git import Commit, GitError, GitRepo, GrepHit
from .memory import Memory
from .paths import MemoryLayout


class StoreService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.memory = Memory(config.memory_dir, config.git_author_name, config.git_author_email)
        config.tasks_dir.mkdir(parents=True, exist_ok=True)


__all__ = [
    "StoreService", "Memory", "MemoryLayout", "GitRepo", "GitError", "Commit", "GrepHit",
    "atomic_write", "read_text",
]

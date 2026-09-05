"""StoreService:持有 memory 仓库(git)和 tasks 根(裸文件)。其余 service 的依赖。"""
from __future__ import annotations

from config import Config

from .files import append_line, atomic_write, read_lines, read_text
from .git import Commit, GitError, GitRepo, GrepHit
from .memory import Memory
from .paths import MemoryLayout, TasksLayout


class StoreService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.memory = Memory(config.memory_dir, config.git_author_name, config.git_author_email)
        config.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.tasks = TasksLayout(config.tasks_dir)


__all__ = [
    "StoreService", "Memory", "MemoryLayout", "TasksLayout", "GitRepo", "GitError", "Commit",
    "GrepHit", "atomic_write", "read_text", "append_line", "read_lines",
]

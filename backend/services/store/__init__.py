"""StoreService:tasks 根(裸文件)。认知层的 git 仓库由 services.collect 管。"""
from __future__ import annotations

from config import Config

from .files import append_line, atomic_write, read_lines, read_text
from .paths import MemoryLayout, TasksLayout


class StoreService:
    def __init__(self, config: Config) -> None:
        self.config = config
        config.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.tasks = TasksLayout(config.tasks_dir)


__all__ = ["StoreService", "MemoryLayout", "TasksLayout", "atomic_write", "read_text", "append_line", "read_lines"]

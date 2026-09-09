"""StoreService:works 根(裸文件)。认知层的 git 仓库由 services.collect 管。"""
from __future__ import annotations

from config import Config

from .files import append_line, atomic_write, read_lines, read_text
from .paths import MemoryLayout, WorksLayout


class StoreService:
    def __init__(self, config: Config) -> None:
        self.config = config
        config.works_dir.mkdir(parents=True, exist_ok=True)
        self.works = WorksLayout(config.works_dir)


__all__ = ["StoreService", "MemoryLayout", "WorksLayout", "atomic_write", "read_text", "append_line", "read_lines"]

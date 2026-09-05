"""运行配置:全部来自环境变量,没有配置文件(store.md:磁盘上只有 git 仓库和裸文件)。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    home: Path                 # ~/.memory.talk
    git_author_name: str
    git_author_email: str

    @property
    def memory_dir(self) -> Path:   # git 仓库:cards/ + issues/
        return self.home / "memory"

    @property
    def tasks_dir(self) -> Path:    # 裸文件:task 树(本轮未实现)
        return self.home / "tasks"


def load_config() -> Config:
    home = Path(os.environ.get("MEMORY_TALK_HOME", "~/.memory.talk")).expanduser()
    return Config(
        home=home,
        git_author_name=os.environ.get("MEMORY_TALK_AUTHOR", "memory.talk"),
        git_author_email=os.environ.get("MEMORY_TALK_EMAIL", "memory.talk@localhost"),
    )

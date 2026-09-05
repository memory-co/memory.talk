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


# ---- task / server 层 ----

def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class RuntimeConfig:
    workspace: Path            # 终端 / agent 类 URI 省略 path 时的默认 cwd
    tmux_socket: str           # tmux -L <socket>,与用户自己的 tmux 隔离
    ttyd_url: str | None       # 终端那扇窗:ttyd 的地址;None = 只有把手没有画面(不撒谎)
    claude_projects: Path      # Claude Code 会话记录根
    codex_sessions: Path       # Codex 会话记录根


def load_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        workspace=Path(_env("MEMORY_TALK_WORKSPACE", "~/workspace")).expanduser(),
        tmux_socket=_env("MEMORY_TALK_TMUX_SOCKET", "memorytalk"),
        ttyd_url=os.environ.get("MEMORY_TALK_TTYD_URL") or None,
        claude_projects=Path(_env("MEMORY_TALK_CLAUDE_PROJECTS", "~/.claude/projects")).expanduser(),
        codex_sessions=Path(_env("MEMORY_TALK_CODEX_SESSIONS", "~/.codex/sessions")).expanduser(),
    )

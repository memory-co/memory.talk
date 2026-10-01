"""运行配置:全部来自环境变量,没有配置文件。work 固定存两个 sqlite(works.db / worktrace.db,docs/designs/v5/work-store.md);
users / auth 的存储介质由 MEMORY_TALK_STORE 选(providers)。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    home: Path                 # ~/.memory.talk
    git_author_name: str
    git_author_email: str
    works_db: Path             # work 的现在:节点、画布、登记、收件箱(MEMORY_TALK_WORKS_DB,默认 <home>/works.db)
    worktrace_db: Path         # work 的经过:段、点、round(MEMORY_TALK_WORKTRACE_DB,默认 <home>/worktrace.db)

    @property
    def metas_dir(self) -> Path:   # 分层 git 仓库(metas)
        return self.home / "metas"

    @property
    def layers_dir(self) -> Path:        # 用户自定义层:每个 .py 一个 Layer 子类,启动时载入
        return self.home / "layers"



def load_config() -> Config:
    home = Path(os.environ.get("MEMORY_TALK_HOME", "~/.memory.talk")).expanduser()
    return Config(
        home=home,
        git_author_name=os.environ.get("MEMORY_TALK_AUTHOR", "memory.talk"),
        git_author_email=os.environ.get("MEMORY_TALK_EMAIL", "memory.talk@localhost"),
        works_db=Path(os.environ.get("MEMORY_TALK_WORKS_DB", str(home / "works.db"))).expanduser(),
        worktrace_db=Path(os.environ.get("MEMORY_TALK_WORKTRACE_DB", str(home / "worktrace.db"))).expanduser(),
    )


# ---- work / server 层 ----

def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class RuntimeConfig:
    workspace: Path            # 终端 / agent 类 URI 省略 path 时的默认 cwd
    tmux_socket: str           # tmuxd 的 socket 名(实际 tmux socket 是 tmuxd-<名>),与用户自己的 tmux 隔离
    tmuxd_state: Path          # tmuxd 的 state 目录(会话记录、ttyd 记录、渲染出的 tmux.conf)
    claude_projects: Path      # Claude Code 会话记录根
    codex_sessions: Path       # Codex 会话记录根
    kimi_sessions: Path        # Kimi Code 会话记录根


def load_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        workspace=Path(_env("MEMORY_TALK_WORKSPACE", "~/workspace")).expanduser(),
        tmux_socket=_env("MEMORY_TALK_TMUX_SOCKET", "memorytalk"),
        tmuxd_state=Path(os.environ.get("MEMORY_TALK_HOME", "~/.memory.talk")).expanduser() / "tmuxd",
        claude_projects=Path(_env("MEMORY_TALK_CLAUDE_PROJECTS", "~/.claude/projects")).expanduser(),
        codex_sessions=Path(_env("MEMORY_TALK_CODEX_SESSIONS", "~/.codex/sessions")).expanduser(),
        kimi_sessions=Path(_env("MEMORY_TALK_KIMI_SESSIONS", "~/.kimi-code/sessions")).expanduser(),
    )

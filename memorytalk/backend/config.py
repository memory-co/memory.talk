"""运行配置:全部来自环境变量,没有配置文件。存储介质由 MEMORY_TALK_STORE 选(providers)。"""
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
    )


# ---- work / server 层 ----

def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class RuntimeConfig:
    workspace: Path            # 终端 / agent 类 URI 省略 path 时的默认 cwd
    tmux_socket: str           # tmuxd 的 socket 名(实际 tmux socket 是 tmuxd-<名>),与用户自己的 tmux 隔离
    tmuxd_state: Path          # tmuxd 的 state 目录(会话记录、ttyd 记录、渲染出的 tmux.conf)
    tmuxd_port: int | None     # ttyd 端口;None = tmuxd 自己挑一个空闲的
    tmuxd_bind: str            # ttyd 绑哪:127.0.0.1(默认)或 0.0.0.0(必须带 token)
    tmuxd_token: str | None    # ttyd 的 basic auth(用户名固定 tmuxd)
    tmuxd_url_host: str | None # 窗地址里写的 host(挂公网时给外部可达的那个)
    claude_projects: Path      # Claude Code 会话记录根
    codex_sessions: Path       # Codex 会话记录根
    kimi_sessions: Path        # Kimi Code 会话记录根


def load_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        workspace=Path(_env("MEMORY_TALK_WORKSPACE", "~/workspace")).expanduser(),
        tmux_socket=_env("MEMORY_TALK_TMUX_SOCKET", "memorytalk"),
        tmuxd_state=Path(os.environ.get("MEMORY_TALK_HOME", "~/.memory.talk")).expanduser() / "tmuxd",
        tmuxd_port=int(os.environ["MEMORY_TALK_TMUXD_PORT"]) if os.environ.get("MEMORY_TALK_TMUXD_PORT") else None,
        tmuxd_bind=_env("MEMORY_TALK_TMUXD_BIND", "127.0.0.1"),
        tmuxd_token=os.environ.get("MEMORY_TALK_TMUXD_TOKEN") or None,
        tmuxd_url_host=os.environ.get("MEMORY_TALK_TMUXD_URL_HOST") or None,
        claude_projects=Path(_env("MEMORY_TALK_CLAUDE_PROJECTS", "~/.claude/projects")).expanduser(),
        codex_sessions=Path(_env("MEMORY_TALK_CODEX_SESSIONS", "~/.codex/sessions")).expanduser(),
        kimi_sessions=Path(_env("MEMORY_TALK_KIMI_SESSIONS", "~/.kimi-code/sessions")).expanduser(),
    )

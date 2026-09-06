"""codex:// —— Codex CLI:终端 + 读 ~/.codex/sessions 的 rollout 记录。"""
from __future__ import annotations

from config import RuntimeConfig
from services.servers.adapters import CodexAdapter
from services.servers.agent import AgentBase


class CodexServer(AgentBase):
    name = "codex"
    description = "Codex:tmux 现场 + 读 ~/.codex/sessions 会话记录"

    def __init__(self, tmux, workspace, ttyd_url, rt: RuntimeConfig) -> None:
        super().__init__(tmux, workspace, ttyd_url, CodexAdapter(rt.codex_sessions))

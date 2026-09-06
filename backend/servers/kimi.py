"""kimi:// —— Kimi Code CLI:终端 + 读 ~/.kimi-code/sessions 的 wire 记录。"""
from __future__ import annotations

from config import RuntimeConfig
from services.servers.adapters import KimiAdapter
from services.servers.agent import AgentBase


class KimiServer(AgentBase):
    name = "kimi"
    description = "Kimi Code:tmux 现场 + 读 ~/.kimi-code/sessions 会话记录"

    def __init__(self, tmux, workspace, ttyd_url, rt: RuntimeConfig) -> None:
        super().__init__(tmux, workspace, ttyd_url, KimiAdapter(rt.kimi_sessions))

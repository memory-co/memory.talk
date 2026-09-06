"""kimi:// —— Kimi Code CLI:终端 + 读 ~/.kimi-code/sessions 的 wire 记录。"""
from __future__ import annotations

from services.servers.adapters import KimiAdapter
from services.servers.agent import AgentBase


class KimiServer(AgentBase):
    name = "kimi"
    protocols = ["kimi"]
    description = "Kimi Code:tmux 现场 + 读 ~/.kimi-code/sessions 会话记录"


def make(ctx):
    return KimiServer(ctx.tmux, ctx.workspace, ctx.ttyd_url, KimiAdapter(ctx.rt.kimi_sessions))

"""codex:// —— Codex CLI:终端 + 读 ~/.codex/sessions 的 rollout 记录。"""
from __future__ import annotations

from services.servers.adapters import CodexAdapter
from services.servers.agent import AgentBase


class CodexServer(AgentBase):
    name = "codex"
    protocols = ["codex"]
    description = "Codex:tmux 现场 + 读 ~/.codex/sessions 会话记录"


def make(ctx):
    return CodexServer(ctx.tmux, ctx.workspace, ctx.ttyd_url, CodexAdapter(ctx.rt.codex_sessions))

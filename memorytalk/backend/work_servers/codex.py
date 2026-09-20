"""codex:// —— Codex CLI:终端 + 读 ~/.codex/sessions 的 rollout 记录。"""
from __future__ import annotations

from memorytalk.backend.services.work_servers.adapters import CodexAdapter
from memorytalk.backend.services.work_servers.agent import AgentBase


class CodexServer(AgentBase):
    name = "codex"
    protocols = ["codex"]
    description = "Codex:tmux 现场 + 读 ~/.codex/sessions 会话记录"


def make(ctx):
    return CodexServer(ctx.tmuxd, ctx.workspace, CodexAdapter(ctx.rt.codex_sessions))

"""claude:// —— Claude Code:终端 + 读 ~/.claude/projects 的会话记录。"""
from __future__ import annotations

from memorytalk.backend.services.work_servers.adapters import ClaudeCodeAdapter
from memorytalk.backend.services.work_servers.agent import AgentBase


class ClaudeServer(AgentBase):
    name = "claude"
    protocols = ["claude"]
    description = "Claude Code:tmux 现场 + 读 ~/.claude/projects 会话记录"


def make(ctx):
    return ClaudeServer(ctx.tmuxd, ctx.workspace, ClaudeCodeAdapter(ctx.rt.claude_projects))

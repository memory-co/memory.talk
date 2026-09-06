"""claude:// —— Claude Code:终端 + 读 ~/.claude/projects 的会话记录。"""
from __future__ import annotations

from services.servers.adapters import ClaudeCodeAdapter
from services.servers.agent import AgentBase


class ClaudeServer(AgentBase):
    name = "claude"
    description = "Claude Code:tmux 现场 + 读 ~/.claude/projects 会话记录"


def make(ctx):
    return ClaudeServer(ctx.tmux, ctx.workspace, ctx.ttyd_url, ClaudeCodeAdapter(ctx.rt.claude_projects))

"""claude:// —— Claude Code:终端 + 读 ~/.claude/projects 的会话记录。"""
from __future__ import annotations

from config import RuntimeConfig
from services.servers.adapters import ClaudeCodeAdapter
from services.servers.agent import AgentBase


class ClaudeServer(AgentBase):
    name = "claude"
    description = "Claude Code:tmux 现场 + 读 ~/.claude/projects 会话记录"

    def __init__(self, tmux, workspace, ttyd_url, rt: RuntimeConfig) -> None:
        super().__init__(tmux, workspace, ttyd_url, ClaudeCodeAdapter(rt.claude_projects))

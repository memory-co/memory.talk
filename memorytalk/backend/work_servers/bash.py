"""bash:// —— 到某目录起一个 bash(tmux 会话)。"""
from __future__ import annotations

from memorytalk.backend.services.work_servers.terminal import TerminalBase


class BashServer(TerminalBase):
    name = "bash"
    protocols = ["bash"]
    description = "bash:///<cwd> → tmux 会话里的 bash"


def make(ctx):
    return BashServer(ctx.tmuxd, ctx.workspace)

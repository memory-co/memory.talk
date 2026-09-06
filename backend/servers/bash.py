"""bash:// —— 到某目录起一个 bash(tmux 会话)。"""
from __future__ import annotations

from services.servers.terminal import TerminalBase


class BashServer(TerminalBase):
    name = "bash"
    description = "bash:///<cwd> → tmux 会话里的 bash"


def make(ctx):
    return BashServer(ctx.tmux, ctx.workspace, ctx.ttyd_url)

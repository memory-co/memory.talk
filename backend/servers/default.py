"""default —— 没有专门 server 的协议都来这里:协议名当命令名,到某目录在 tmux 里跑。
`vim:///notes.md` = cd 到父目录 && vim notes.md;`htop://` = htop。调用方不用感知它背后是 bash。"""
from __future__ import annotations

from models.server import ParsedUri
from services.servers.terminal import TerminalBase


class DefaultServer(TerminalBase):
    name = "default"
    protocols: list[str] = []          # 不声明任何协议:只当兜底
    description = "兜底:没有专门 server 的协议,把协议名当命令名在 tmux 里跑"

    def command(self, uri: ParsedUri) -> str:
        return uri.scheme


def make(ctx):
    return DefaultServer(ctx.tmux, ctx.workspace, ctx.ttyd_url)

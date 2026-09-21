"""default —— 没有专门 server 的协议都来这里:协议名当命令名,到某目录在 tmux 里跑。
`vim:///notes.md` = cd 到父目录 && vim notes.md;`htop://` = htop。调用方不用感知它背后是 bash。"""
from __future__ import annotations

from pathlib import Path

from tmuxd import Tmuxd

from memorytalk.backend.models.work_server import Live, ParsedUri, WorkServerInfo, Window
from memorytalk.backend.services.work_servers.terminal import TmuxHandle, kill_session, open_session, resolve_command, session_window


class DefaultServer:
    name = "default"
    protocols: list[str] = []          # 不声明任何协议:只当兜底
    description = "兜底:没有专门 server 的协议,把协议名当命令名在 tmux 里跑"

    def __init__(self, tmuxd: Tmuxd, workspace: Path) -> None:
        self.tmuxd = tmuxd                      # 进程里那一份 tmuxd,启动时注入
        self.workspace = workspace              # URI 没给 path 时的默认 cwd

    def info(self) -> WorkServerInfo:
        return WorkServerInfo(name=self.name, protocols=self.protocols, description=self.description)

    def open(self, worklet_id: str, uri: ParsedUri, since_mtime: float = 0.0) -> tuple[Live, TmuxHandle]:
        cwd, argv = resolve_command(uri, self.workspace, uri.scheme)
        session = open_session(self.tmuxd, worklet_id, cwd, argv)          # tmuxd.session(id, cwd, cmd):有就取回,没有就建
        handle = TmuxHandle(self.tmuxd, worklet_id)
        return Live(worklet_id=worklet_id, server=self.name, window=Window(url=session.url, embed=session.url),
                    handle=handle.info(), cwd=str(cwd), command=argv), handle

    def handle(self, worklet_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> TmuxHandle:
        return TmuxHandle(self.tmuxd, worklet_id)

    def alive(self, worklet_id: str) -> bool:
        return self.tmuxd.has(worklet_id)

    def window(self, worklet_id: str, uri: ParsedUri) -> Window:
        return session_window(self.tmuxd, worklet_id)

    def destroy(self, worklet_id: str) -> None:
        kill_session(self.tmuxd, worklet_id)


def make(ctx):
    return DefaultServer(ctx.tmuxd, ctx.workspace)

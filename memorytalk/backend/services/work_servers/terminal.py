"""终端类 server 的基类:实现面是 tmuxd(pip 库,tmux + ttyd)。具体的 server 在 backend/work_servers/ 里,各自声明响应哪些协议。

现场 = tmuxd 的 session(id = 工作单元 id),活得比连接久;
窗   = session.url(ttyd 跟着 tmuxd 自带);
把手 = session(alive / send / send_key / kill)。只写不读——抓屏不存在(docs/designs/v5/work-server.md §6)。
"""
from __future__ import annotations

import shlex
import shutil
from pathlib import Path

from tmuxd import Session, Tmuxd, TmuxdError

from memorytalk.backend.models.work_server import HandleInfo, Live, ParsedUri, WorkServerError, WorkServerInfo, Window


class TmuxHandle:
    """把手:包一层 tmuxd 的 Session。按 id 懒取——现场可能已经退出了(命令跑完了),把手照样能回答「活没活着」。"""

    def __init__(self, tmuxd: Tmuxd, worklet_id: str) -> None:
        self.tmuxd, self.worklet_id = tmuxd, worklet_id

    def info(self) -> HandleInfo:
        return HandleInfo(kind="tmux", capabilities=["send"])

    def alive(self) -> bool:
        return self.tmuxd.has(self.worklet_id)

    def session(self) -> Session:
        return self.tmuxd.get(self.worklet_id)          # 没了 → NoSuchSession

    def send(self, text: str, enter: bool = True) -> None:
        self.session().send(text, enter=enter)


class TerminalBase:
    """「到某目录跑某命令」这一族 server 的公共实现。子类只定 name(= 协议名 = 命令名)。"""
    name = "terminal"
    protocols: list[str] = []
    description = ""

    def __init__(self, tmuxd: Tmuxd, workspace: Path) -> None:
        self.tmuxd, self.workspace = tmuxd, workspace

    def info(self) -> WorkServerInfo:
        return WorkServerInfo(name=self.name, protocols=self.protocols, description=self.description)

    def command(self, uri: ParsedUri) -> str:
        """要跑的命令名;默认 = server 名。default server 改成用协议名。"""
        return self.name

    def resolve(self, uri: ParsedUri) -> tuple[Path, list[str]]:
        cmd = self.command(uri)
        if shutil.which(cmd) is None:
            raise WorkServerError("cmd_not_found", f"PATH 里没有 {cmd!r};装上它")
        path = Path(uri.path) if uri.path and uri.path != "/" else self.workspace
        if path.is_file():
            return path.parent, [cmd, path.name]
        return path, [cmd]

    def open(self, worklet_id: str, uri: ParsedUri, since_mtime: float = 0.0) -> tuple[Live, TmuxHandle]:
        cwd, cmd = self.resolve(uri)
        cwd.mkdir(parents=True, exist_ok=True)
        try:
            session = self.tmuxd.session(id=worklet_id, cwd=str(cwd), cmd=shlex.join(cmd))   # 幂等:有就取回,没有就建
        except TmuxdError as e:
            raise WorkServerError("platform", f"tmuxd: {e}") from e
        handle = self.handle(worklet_id, uri, cwd, since_mtime)
        return Live(worklet_id=worklet_id, server=self.name, window=Window(url=session.url, embed=session.url),
                    handle=handle.info(), cwd=str(cwd), command=cmd), handle

    def handle(self, worklet_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> TmuxHandle:
        return TmuxHandle(self.tmuxd, worklet_id)

    def alive(self, worklet_id: str) -> bool:
        return self.tmuxd.has(worklet_id)

    def window(self, worklet_id: str, uri: ParsedUri) -> Window:
        """那扇窗的地址,不用重新 open:tmuxd 的 ttyd 地址只由 id 决定。"""
        url = self.tmuxd.url_for(worklet_id)
        return Window(url=url, embed=url)

    def destroy(self, worklet_id: str) -> None:
        if self.tmuxd.has(worklet_id):
            self.tmuxd.get(worklet_id).kill()

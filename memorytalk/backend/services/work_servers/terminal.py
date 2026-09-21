"""终端类 server 共用的小件——不是基类。每个 server 自己写 __init__(拿注入的 tmuxd)和 open(调 tmuxd.session 把现场开起来),
像 controller 一样一眼能看到;这里只放三样它们都要用的:解析「到哪个目录跑什么」、把 tmuxd 的错误变成 WorkServerError、tmux 把手。

实现面是 tmuxd(pip 库,tmux + ttyd):现场 = session(id = 工作单元 id),窗 = session.url,把手 = session(只写不读)。
"""
from __future__ import annotations

import shlex
import shutil
from pathlib import Path
from typing import Protocol

from tmuxd import Session, Tmuxd, TmuxdError

from memorytalk.backend.models.work_server import HandleInfo, Live, ParsedUri, WorkServerError, WorkServerInfo, Window


class WorkServer(Protocol):
    """一个 server 的契约面(docs/designs/v5/work-server.md §3):声明协议、幂等建 / 取现场、交回窗和把手。"""
    name: str
    protocols: list[str]
    description: str

    def info(self) -> WorkServerInfo: ...
    def open(self, worklet_id: str, uri: ParsedUri, since_mtime: float = 0.0) -> tuple[Live, object]: ...
    def handle(self, worklet_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> object: ...
    def alive(self, worklet_id: str) -> bool: ...
    def window(self, worklet_id: str, uri: ParsedUri) -> Window: ...
    def destroy(self, worklet_id: str) -> None: ...


def resolve_command(uri: ParsedUri, workspace: Path, cmd: str) -> tuple[Path, list[str]]:
    """URI → (cwd, argv):path 是目录就 cd 进去跑 cmd;是文件就 cd 到父目录、文件名当参数;空 = 默认工作区。命令不在 PATH → cmd_not_found。"""
    if shutil.which(cmd) is None:
        raise WorkServerError("cmd_not_found", f"PATH 里没有 {cmd!r};装上它")
    path = Path(uri.path) if uri.path and uri.path != "/" else workspace
    if path.is_file():
        return path.parent, [cmd, path.name]
    return path, [cmd]


def open_session(tmuxd: Tmuxd, worklet_id: str, cwd: Path, argv: list[str]) -> Session:
    """幂等:有就取回,没有就建(tmux new -A 的语义);tmuxd 建不出来 → platform。"""
    cwd.mkdir(parents=True, exist_ok=True)
    try:
        return tmuxd.session(id=worklet_id, cwd=str(cwd), cmd=shlex.join(argv))
    except TmuxdError as e:
        raise WorkServerError("platform", f"tmuxd: {e}") from e


def session_window(tmuxd: Tmuxd, worklet_id: str) -> Window:
    """那扇窗:tmuxd 自带的 ttyd 地址,只由 id 决定,不用重新 open。"""
    url = tmuxd.url_for(worklet_id)
    return Window(url=url, embed=url)


def kill_session(tmuxd: Tmuxd, worklet_id: str) -> None:
    if tmuxd.has(worklet_id):
        tmuxd.get(worklet_id).kill()


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

"""tmux 现场 + 终端类 server 的基类(蓝本 tmuxd)。具体协议的 server 在 backend/servers/ 里,server 名 = 协议名 = 命令名。

现场 = tmux 会话(名字 = 成员 id),活得比连接久;
窗   = ttyd(配置了地址才有;没配就老实报 None);
把手 = send-keys / capture-pane / has-session。
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from models.server import HandleInfo, Live, ParsedUri, ServerError, ServerInfo, Window


class Tmux:
    def __init__(self, socket: str) -> None:
        self.socket = socket

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["tmux", "-L", self.socket, *args], capture_output=True, text=True)

    def has(self, name: str) -> bool:
        return self._run("has-session", "-t", f"={name}").returncode == 0

    def new(self, name: str, cwd: Path, cmd: list[str]) -> None:
        cwd.mkdir(parents=True, exist_ok=True)
        p = self._run("new-session", "-d", "-s", name, "-c", str(cwd), shlex.join(cmd))
        if p.returncode != 0:
            raise ServerError("platform", f"tmux new-session 失败: {p.stderr.strip()}")

    def kill(self, name: str) -> None:
        self._run("kill-session", "-t", f"={name}")

    def send(self, name: str, text: str, enter: bool = True) -> None:
        args = ["send-keys", "-t", f"{name}:", text]
        if enter:
            args.append("Enter")
        self._run(*args)

    def capture(self, name: str, lines: int = 200) -> str:
        return self._run("capture-pane", "-p", "-t", f"{name}:", "-S", f"-{lines}").stdout


class TmuxHandle:
    def __init__(self, tmux: Tmux, name: str) -> None:
        self.tmux, self.name = tmux, name

    def info(self) -> HandleInfo:
        return HandleInfo(kind="tmux", capabilities=["capture", "send"])

    def alive(self) -> bool:
        return self.tmux.has(self.name)

    def capture(self, lines: int = 200) -> str:
        return self.tmux.capture(self.name, lines)

    def send(self, text: str, enter: bool = True) -> None:
        self.tmux.send(self.name, text, enter)


class TerminalBase:
    """「到某目录跑某命令」这一族 server 的公共实现。子类只定 name(= 协议名 = 命令名)。"""
    name = "terminal"
    description = ""

    def __init__(self, tmux: Tmux, workspace: Path, ttyd_url: str | None) -> None:
        self.tmux, self.workspace, self.ttyd_url = tmux, workspace, ttyd_url

    def info(self) -> ServerInfo:
        return ServerInfo(name=self.name, description=self.description)

    def command(self, uri: ParsedUri) -> str:
        """要跑的命令名;默认 = server 名 = 协议名。"""
        return self.name

    def resolve(self, uri: ParsedUri) -> tuple[Path, list[str]]:
        cmd = self.command(uri)
        if shutil.which(cmd) is None:
            raise ServerError("cmd_not_found", f"PATH 里没有 {cmd!r};装上它")
        path = Path(uri.path) if uri.path and uri.path != "/" else self.workspace
        if path.is_file():
            return path.parent, [cmd, path.name]
        return path, [cmd]

    def open(self, member_id: str, uri: ParsedUri, since_mtime: float = 0.0) -> tuple[Live, TmuxHandle]:
        cwd, cmd = self.resolve(uri)
        if not self.tmux.has(member_id):
            self.tmux.new(member_id, cwd, cmd)
        handle = self.handle(member_id, uri, cwd, since_mtime)
        url = f"{self.ttyd_url.rstrip('/')}/?arg={member_id}" if self.ttyd_url else None
        return Live(member_id=member_id, server=self.name, window=Window(url=url, embed=url),
                    handle=handle.info(), cwd=str(cwd), command=cmd), handle

    def handle(self, member_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> TmuxHandle:
        return TmuxHandle(self.tmux, member_id)

    def alive(self, member_id: str) -> bool:
        return self.tmux.has(member_id)

    def destroy(self, member_id: str) -> None:
        self.tmux.kill(member_id)

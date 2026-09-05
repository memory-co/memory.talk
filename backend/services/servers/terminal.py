"""终端 server:bash:// 以及任何 PATH 里有的命令名 → tmux 会话(蓝本 tmuxd)。

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


class TerminalServer:
    name = "terminal"
    description = "bash:// 与任何 PATH 里的命令名 → tmux 会话"

    def __init__(self, tmux: Tmux, workspace: Path, ttyd_url: str | None) -> None:
        self.tmux, self.workspace, self.ttyd_url = tmux, workspace, ttyd_url

    def info(self) -> ServerInfo:
        return ServerInfo(name=self.name, claims=["*"], description=self.description)

    # 约定优于注册:scheme 名即命令名,PATH 里有就认领
    def claims(self, scheme: str) -> bool:
        return shutil.which(scheme) is not None

    def resolve_command(self, uri: ParsedUri) -> tuple[Path, list[str]]:
        exe = shutil.which(uri.scheme)
        if exe is None:
            raise ServerError("cmd_not_found", f"PATH 里没有 {uri.scheme!r};装上它,或换一个协议")
        path = Path(uri.path) if uri.path and uri.path != "/" else self.workspace
        if path.is_file():
            return path.parent, [uri.scheme, path.name]
        return path, [uri.scheme]

    def open(self, member_id: str, uri: ParsedUri) -> tuple[Live, TmuxHandle]:
        cwd, cmd = self.resolve_command(uri)
        if not self.tmux.has(member_id):
            self.tmux.new(member_id, cwd, cmd)
        handle = TmuxHandle(self.tmux, member_id)
        url = f"{self.ttyd_url.rstrip('/')}/?arg={member_id}" if self.ttyd_url else None
        live = Live(member_id=member_id, server=self.name, window=Window(url=url, embed=url),
                    handle=handle.info(), cwd=str(cwd), command=cmd)
        return live, handle

    def handle(self, member_id: str) -> TmuxHandle:
        return TmuxHandle(self.tmux, member_id)

    def alive(self, member_id: str) -> bool:
        return self.tmux.has(member_id)

    def destroy(self, member_id: str) -> None:
        self.tmux.kill(member_id)

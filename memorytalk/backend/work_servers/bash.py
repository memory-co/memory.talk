"""bash:// —— 到某目录起一个 bash(tmuxd session),它的每条命令进 trace(work-server-io.md §6)。

新起的 bash 带上 `--rcfile`(node/layout.py 生成):先读用户自己的 ~/.bashrc,再装上记命令的钩子——每条命令开始、结束各记一行事件,
输出取那一段屏幕;节点读了推进 trace,和 claude 一样有「记录」。bash:///<文件> 是跑一个脚本,跑完现场就没了,不记。
"""
from __future__ import annotations

from pathlib import Path

from tmuxd import Tmuxd

from memorytalk.backend.models.work_server import HandleInfo, Live, ParsedUri, WorkServerInfo, Window
from memorytalk.backend.services.work_servers.terminal import TmuxHandle, kill_session, open_session, resolve_command, session_window
from memorytalk.node import layout


class BashHandle(TmuxHandle):
    def __init__(self, tmuxd: Tmuxd, worklet_id: str, recorded: bool) -> None:
        super().__init__(tmuxd, worklet_id)
        self.recorded = recorded

    def info(self) -> HandleInfo:
        return HandleInfo(kind="tmux", capabilities=["input.text", "input.keys"] + (["trace.agent"] if self.recorded else []))


def _script(uri: ParsedUri) -> bool:
    """bash:///<文件> = 跑这个脚本(resolve_command 的同一个判断)。"""
    return bool(uri.path and uri.path != "/" and Path(uri.path).is_file())


class BashServer:
    name = "bash"
    protocols = ["bash"]
    description = "bash:///<cwd> → tmux 会话里的 bash;每条命令进 trace"

    def __init__(self, tmuxd: Tmuxd, workspace: Path, node_dir: Path) -> None:
        self.tmuxd = tmuxd                      # 进程里那一份 tmuxd,启动时注入
        self.workspace = workspace              # URI 没给 path 时的默认 cwd
        self.node_dir = node_dir                # 节点的状态目录:命令事件写到这下面

    def info(self) -> WorkServerInfo:
        return WorkServerInfo(name=self.name, protocols=self.protocols, description=self.description)

    def open(self, worklet_id: str, uri: ParsedUri, since_mtime: float = 0.0) -> tuple[Live, BashHandle]:
        cwd, argv = resolve_command(uri, self.workspace, "bash")
        if not _script(uri) and not self.tmuxd.has(worklet_id):          # 新起一个交互的 bash:装上记命令的钩子
            argv = ["bash", "--rcfile", str(layout.bash_rc(self.node_dir, worklet_id)), "-i"]
        session = open_session(self.tmuxd, worklet_id, cwd, argv)          # tmuxd.session(id, cwd, cmd):有就取回,没有就建
        handle = self.handle(worklet_id, uri, cwd, since_mtime)
        return Live(worklet_id=worklet_id, server=self.name, window=Window(url=session.url, embed=session.url),
                    handle=handle.info(), cwd=str(cwd), command=argv), handle

    def handle(self, worklet_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> BashHandle:
        return BashHandle(self.tmuxd, worklet_id, recorded=self._recorded(worklet_id, uri))

    def watch_spec(self, worklet_id: str, uri: ParsedUri | None = None) -> dict | None:
        """节点盯它要知道的:命令事件文件、tmux socket。不记的(跑脚本的、装钩子之前就起的老现场)交回 None。"""
        if not self._recorded(worklet_id, uri):
            return None
        return {"hooks": str(layout.hooks_file(self.node_dir, worklet_id)), "tmux_socket": self.tmuxd.tmux_socket}

    def _recorded(self, worklet_id: str, uri: ParsedUri | None) -> bool:
        """这个 bash 是带着钩子起的:不是跑脚本,而且开的时候写过 rcfile(装钩子之前就起的老现场没有,不假装有记录)。"""
        return not (uri is not None and _script(uri)) and (layout.worklet_dir(self.node_dir, worklet_id) / "bashrc").exists()

    def alive(self, worklet_id: str) -> bool:
        return self.tmuxd.has(worklet_id)

    def window(self, worklet_id: str, uri: ParsedUri) -> Window:
        return session_window(self.tmuxd, worklet_id)

    def destroy(self, worklet_id: str) -> None:
        kill_session(self.tmuxd, worklet_id)


def make(ctx):
    return BashServer(ctx.tmuxd, ctx.workspace, ctx.rt.node_dir)

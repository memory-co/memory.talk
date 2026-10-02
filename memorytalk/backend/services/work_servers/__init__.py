"""WorkServerService:协议 → server 的请求入口(docs/designs/v5/protocol-server.md)。
具体 server 住在 backend/servers/(各自声明响应哪些协议;没人声明的去 default),这里只做装载与寻址。"""
from __future__ import annotations

from pathlib import Path

from memorytalk.backend.config import RuntimeConfig
from memorytalk.backend.models.work_server import Live, WorkServerError, WorkServerInfo

from .registry import Registry
from .uri import parse_uri

class WorkServerService:
    def __init__(self, rt: RuntimeConfig, surface_path: str) -> None:
        from tmuxd import Tmuxd
        from memorytalk.backend import work_servers  # backend/work_servers/
        self.rt = rt
        # 一个进程一份 tmuxd:自己的 tmux socket(tmuxd-<名>)、自己的 ttyd(这一行之后就起来了)、state 在 <home>/tmuxd/。
        # ttyd 听 state 目录里的 unix socket,不占端口;窗 = <surface_path>/tmuxd/?arg=<id>,经 surfaces() 交给 main.py 挂上(work-server.md §7)
        self.tmuxd = Tmuxd(listen="unix", base_path=f"{surface_path}/tmuxd", socket=rt.tmux_socket, workspace=str(rt.workspace),
                           state_dir=str(rt.tmuxd_state))
        self.registry = Registry(work_servers.load(rt, self.tmuxd))

    def surfaces(self) -> list[tuple[str, object]]:
        """这个进程里所有的窗:(挂载点, ASGI app),挂载点就是各自的 base_path。门不在这里,在 gateway.AuthMiddleware。"""
        return [(self.tmuxd.base_path, self.tmuxd.asgi())]

    def close(self) -> None:
        """进程退出:收掉自己起的 ttyd;tmux 会话不是我们的,照跑。"""
        self.tmuxd.close()

    def list(self) -> list[WorkServerInfo]:
        return self.registry.infos()

    def resolve(self, raw_uri: str):
        uri = parse_uri(raw_uri)
        return uri, self.registry.resolve(uri)

    def open(self, worklet_id: str, raw_uri: str, since_mtime: float = 0.0) -> tuple[Live, object]:
        uri, server = self.resolve(raw_uri)
        return server.open(worklet_id, uri, since_mtime)

    def handle(self, server_name: str, worklet_id: str, raw_uri: str, cwd: str | None, since_mtime: float):
        return self.registry.by_name(server_name).handle(worklet_id, parse_uri(raw_uri), Path(cwd or "."), since_mtime)

    def alive(self, server_name: str, worklet_id: str) -> bool:
        return self.registry.by_name(server_name).alive(worklet_id)

    def watch_spec(self, server_name: str, worklet_id: str) -> dict | None:
        """走推的 server(agent 的 output 由节点读了推进 trace):节点盯它要知道的那几样(hooks 文件、会话记录根、tmux socket)。
        不走推的(终端、网页,还有还在旧路径上的 Codex / Kimi)交回 None。"""
        s = self.registry.by_name(server_name)
        return s.watch_spec(worklet_id) if hasattr(s, "watch_spec") else None

    def window(self, server_name: str, worklet_id: str, raw_uri: str):
        return self.registry.by_name(server_name).window(worklet_id, parse_uri(raw_uri))

    def destroy(self, server_name: str, worklet_id: str) -> None:
        self.registry.by_name(server_name).destroy(worklet_id)


__all__ = ["WorkServerService", "WorkServerError", "parse_uri"]

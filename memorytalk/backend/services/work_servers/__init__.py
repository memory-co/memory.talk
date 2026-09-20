"""WorkServerService:协议 → server 的请求入口(docs/designs/v5/protocol-server.md)。
具体 server 住在 backend/servers/(各自声明响应哪些协议;没人声明的去 default),这里只做装载与寻址。"""
from __future__ import annotations

from pathlib import Path

from memorytalk.backend.config import RuntimeConfig
from memorytalk.backend.models.work_server import Live, WorkServerError, WorkServerInfo

from .registry import Registry
from .uri import parse_uri


class WorkServerService:
    def __init__(self, rt: RuntimeConfig) -> None:
        from tmuxd import Tmuxd
        from memorytalk.backend import work_servers  # backend/work_servers/
        self.rt = rt
        # 一个进程一份 tmuxd:自己的 tmux socket(tmuxd-<名>)、自己的 ttyd(这一行之后就起来了)、state 在 <home>/tmuxd/
        self.tmuxd = Tmuxd(rt.tmuxd_port, bind=rt.tmuxd_bind, token=rt.tmuxd_token, socket=rt.tmux_socket, workspace=str(rt.workspace),
                           state_dir=str(rt.tmuxd_state), url_host=rt.tmuxd_url_host)
        self.registry = Registry(work_servers.load(rt, self.tmuxd))

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

    def window(self, server_name: str, worklet_id: str, raw_uri: str):
        return self.registry.by_name(server_name).window(worklet_id, parse_uri(raw_uri))

    def destroy(self, server_name: str, worklet_id: str) -> None:
        self.registry.by_name(server_name).destroy(worklet_id)


__all__ = ["WorkServerService", "WorkServerError", "parse_uri"]

"""协议 → server:先查各 server 自己声明的 protocols;没人声明的协议去 default。"""
from __future__ import annotations

from models.server import ParsedUri, ServerError, ServerInfo


class Registry:
    def __init__(self, servers: list, default: str = "default") -> None:
        self.servers = {s.name: s for s in servers}
        self.by_protocol = {}
        for s in servers:
            for p in getattr(s, "protocols", []):
                self.by_protocol.setdefault(p, s)
        self.default = self.servers.get(default)

    def resolve(self, uri: ParsedUri):
        s = self.by_protocol.get(uri.scheme) or self.default
        if s is None:
            raise ServerError("no_server", f"没有 server 响应 {uri.scheme}://,也没有 default server")
        return s

    def by_name(self, name: str):
        try:
            return self.servers[name]
        except KeyError:
            raise ServerError("no_server", f"没有叫 {name!r} 的 server") from None

    def infos(self) -> list[ServerInfo]:
        return [s.info() for s in self.servers.values()]

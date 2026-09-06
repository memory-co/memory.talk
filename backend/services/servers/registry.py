"""协议 → server:名字就是协议名,查表;没有就明确报错,不兜底。"""
from __future__ import annotations

from models.server import ParsedUri, ServerError, ServerInfo


class Registry:
    def __init__(self, servers: dict[str, object]) -> None:
        self.servers = servers

    def resolve(self, uri: ParsedUri):
        return self.by_name(uri.scheme)

    def by_name(self, name: str):
        try:
            return self.servers[name]
        except KeyError:
            raise ServerError("no_server", f"没有 {name}:// 这个 server(backend/servers/ 里没有 {name}.py)") from None

    def infos(self) -> list[ServerInfo]:
        return [s.info() for s in self.servers.values()]

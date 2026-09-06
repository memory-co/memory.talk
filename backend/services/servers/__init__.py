"""ServerService:协议 → server 的请求入口(docs/works/v5/protocol-server.md)。
具体 server 住在 backend/servers/(一个协议一个文件),这里只做装载与分发。"""
from __future__ import annotations

from pathlib import Path

from config import RuntimeConfig
from models.server import Live, ServerError, ServerInfo

from .registry import Registry
from .uri import parse_uri


class ServerService:
    def __init__(self, rt: RuntimeConfig) -> None:
        import servers  # backend/servers/
        self.rt = rt
        explicit, fallback = servers.load(rt)
        self.registry = Registry(explicit=explicit, fallback=fallback)

    def list(self) -> list[ServerInfo]:
        return self.registry.infos()

    def resolve(self, raw_uri: str):
        uri = parse_uri(raw_uri)
        return uri, self.registry.resolve(uri)

    def open(self, member_id: str, raw_uri: str, since_mtime: float = 0.0) -> tuple[Live, object]:
        uri, server = self.resolve(raw_uri)
        return server.open(member_id, uri, since_mtime)

    def handle(self, server_name: str, member_id: str, raw_uri: str, cwd: str | None, since_mtime: float):
        return self.registry.by_name(server_name).handle(member_id, parse_uri(raw_uri), Path(cwd or "."), since_mtime)

    def alive(self, server_name: str, member_id: str) -> bool:
        return self.registry.by_name(server_name).alive(member_id)

    def destroy(self, server_name: str, member_id: str) -> None:
        self.registry.by_name(server_name).destroy(member_id)


__all__ = ["ServerService", "ServerError", "parse_uri"]

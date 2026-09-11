"""ProtocolServerService:协议 → server 的请求入口(docs/designs/v5/protocol-server.md)。
具体 server 住在 backend/servers/(各自声明响应哪些协议;没人声明的去 default),这里只做装载与寻址。"""
from __future__ import annotations

from pathlib import Path

from config import RuntimeConfig
from models.protocol_server import Live, ProtocolServerError, ProtocolServerInfo

from .registry import Registry
from .uri import parse_uri


class ProtocolServerService:
    def __init__(self, rt: RuntimeConfig) -> None:
        import protocol_servers  # backend/protocol_servers/
        self.rt = rt
        self.registry = Registry(protocol_servers.load(rt))

    def list(self) -> list[ProtocolServerInfo]:
        return self.registry.infos()

    def resolve(self, raw_uri: str):
        uri = parse_uri(raw_uri)
        return uri, self.registry.resolve(uri)

    def open(self, session_id: str, raw_uri: str, since_mtime: float = 0.0) -> tuple[Live, object]:
        uri, server = self.resolve(raw_uri)
        return server.open(session_id, uri, since_mtime)

    def handle(self, server_name: str, session_id: str, raw_uri: str, cwd: str | None, since_mtime: float):
        return self.registry.by_name(server_name).handle(session_id, parse_uri(raw_uri), Path(cwd or "."), since_mtime)

    def alive(self, server_name: str, session_id: str) -> bool:
        return self.registry.by_name(server_name).alive(session_id)

    def destroy(self, server_name: str, session_id: str) -> None:
        self.registry.by_name(server_name).destroy(session_id)


__all__ = ["ProtocolServerService", "ProtocolServerError", "parse_uri"]

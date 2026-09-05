"""ServerService:协议 → server 的请求入口(docs/works/v5/protocol-server.md)。"""
from __future__ import annotations

from config import RuntimeConfig
from models.server import Live, ParsedUri, ServerError, ServerInfo

from .adapters import ClaudeCodeAdapter, CodexAdapter
from .agent import AgentServer
from .browser import BrowserServer
from .files import FilesServer
from .registry import Registry
from .terminal import TerminalServer, Tmux
from .uri import parse_uri


class ServerService:
    def __init__(self, rt: RuntimeConfig) -> None:
        self.rt = rt
        self.terminal = TerminalServer(Tmux(rt.tmux_socket), rt.workspace, rt.ttyd_url)
        self.agent = AgentServer(self.terminal, {
            "claude": ClaudeCodeAdapter(rt.claude_projects),
            "codex": CodexAdapter(rt.codex_sessions),
        })
        self.browser = BrowserServer()
        self.files = FilesServer()
        self.registry = Registry(explicit=[self.agent, self.browser, self.files], fallback=[self.terminal])

    def list(self) -> list[ServerInfo]:
        return self.registry.infos()

    def resolve(self, raw_uri: str):
        uri = parse_uri(raw_uri)
        return uri, self.registry.resolve(uri)

    def open(self, member_id: str, raw_uri: str, since_mtime: float = 0.0) -> tuple[Live, object]:
        uri, server = self.resolve(raw_uri)
        if server is self.agent:
            return self.agent.open(member_id, uri, since_mtime)
        return server.open(member_id, uri)

    def alive(self, server_name: str, member_id: str) -> bool:
        return self.registry.by_name(server_name).alive(member_id)

    def destroy(self, server_name: str, member_id: str) -> None:
        self.registry.by_name(server_name).destroy(member_id)


__all__ = ["ServerService", "ServerError", "parse_uri"]

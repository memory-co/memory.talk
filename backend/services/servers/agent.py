"""agent server:claude:// codex:// —— 现场同终端(tmux),把手多一项「读会话 round」。"""
from __future__ import annotations

from pathlib import Path

from models.server import HandleInfo, Live, ParsedUri, ServerInfo
from models.task import Round

from .adapters import TranscriptAdapter
from .terminal import TerminalServer, TmuxHandle


class AgentHandle(TmuxHandle):
    def __init__(self, base: TmuxHandle, adapter: TranscriptAdapter, cwd: Path, since_mtime: float) -> None:
        super().__init__(base.tmux, base.name)
        self.adapter, self.cwd, self.since_mtime = adapter, cwd, since_mtime

    def info(self) -> HandleInfo:
        return HandleInfo(kind="tmux+transcript", capabilities=["capture", "send", "rounds"])

    def transcript(self) -> Path | None:
        return self.adapter.find(self.cwd, self.since_mtime)

    def rounds(self) -> list[Round]:
        p = self.transcript()
        return self.adapter.rounds(p) if p else []


class AgentServer:
    name = "agent"
    description = "已知的 code agent CLI(claude / codex):终端 + 读会话记录"

    def __init__(self, terminal: TerminalServer, adapters: dict[str, TranscriptAdapter]) -> None:
        self.terminal, self.adapters = terminal, adapters

    def info(self) -> ServerInfo:
        return ServerInfo(name=self.name, claims=sorted(self.adapters), description=self.description)

    def claims(self, scheme: str) -> bool:
        return scheme in self.adapters

    def open(self, member_id: str, uri: ParsedUri, since_mtime: float = 0.0) -> tuple[Live, AgentHandle]:
        live, base = self.terminal.open(member_id, uri)
        handle = AgentHandle(base, self.adapters[uri.scheme], Path(live.cwd or "."), since_mtime)
        live = live.model_copy(update={"server": self.name, "handle": handle.info()})
        return live, handle

    def handle(self, member_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> AgentHandle:
        return AgentHandle(self.terminal.handle(member_id), self.adapters[uri.scheme], cwd, since_mtime)

    def alive(self, member_id: str) -> bool:
        return self.terminal.alive(member_id)

    def destroy(self, member_id: str) -> None:
        self.terminal.destroy(member_id)

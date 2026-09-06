"""agent 类 server 的基类:现场同终端(tmux),把手多一项「读会话 round」。"""
from __future__ import annotations

from pathlib import Path

from models.server import HandleInfo, ParsedUri
from models.task import Round

from .adapters import TranscriptAdapter
from .terminal import TerminalBase, Tmux, TmuxHandle


class AgentHandle(TmuxHandle):
    def __init__(self, tmux: Tmux, name: str, adapter: TranscriptAdapter, cwd: Path, since_mtime: float) -> None:
        super().__init__(tmux, name)
        self.adapter, self.cwd, self.since_mtime = adapter, cwd, since_mtime

    def info(self) -> HandleInfo:
        return HandleInfo(kind="tmux+transcript", capabilities=["capture", "send", "rounds"])

    def transcript(self) -> Path | None:
        return self.adapter.find(self.cwd, self.since_mtime)

    def rounds(self) -> list[Round]:
        p = self.transcript()
        return self.adapter.rounds(p) if p else []


class AgentBase(TerminalBase):
    """子类只需给 name + adapter。"""
    description = "code agent CLI:终端 + 读会话记录"

    def __init__(self, tmux: Tmux, workspace: Path, ttyd_url: str | None, adapter: TranscriptAdapter) -> None:
        super().__init__(tmux, workspace, ttyd_url)
        self.adapter = adapter

    def handle(self, session_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> AgentHandle:
        return AgentHandle(self.tmux, session_id, self.adapter, cwd, since_mtime)

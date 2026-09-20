"""agent 类 server 的基类:现场同终端(tmux),把手多一项「读工作单元 round」。"""
from __future__ import annotations

from pathlib import Path

from memorytalk.backend.models.work_server import HandleInfo, ParsedUri
from memorytalk.backend.models.work import Round

from .adapters import TranscriptAdapter
from tmuxd import Tmuxd

from .terminal import TerminalBase, TmuxHandle


class AgentHandle(TmuxHandle):
    def __init__(self, tmuxd: Tmuxd, worklet_id: str, adapter: TranscriptAdapter, cwd: Path, since_mtime: float) -> None:
        super().__init__(tmuxd, worklet_id)
        self.adapter, self.cwd, self.since_mtime = adapter, cwd, since_mtime

    def info(self) -> HandleInfo:
        return HandleInfo(kind="tmux+transcript", capabilities=["send", "rounds"])

    def transcript(self) -> Path | None:
        return self.adapter.find(self.cwd, self.since_mtime)

    def rounds(self) -> list[Round]:
        p = self.transcript()
        return self.adapter.rounds(p) if p else []


class AgentBase(TerminalBase):
    """子类只需给 name + adapter。"""
    description = "code agent CLI:终端 + 读会话记录"

    def __init__(self, tmuxd: Tmuxd, workspace: Path, adapter: TranscriptAdapter) -> None:
        super().__init__(tmuxd, workspace)
        self.adapter = adapter

    def handle(self, worklet_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> AgentHandle:
        return AgentHandle(self.tmuxd, worklet_id, self.adapter, cwd, since_mtime)

"""agent 类 server 共用的把手:终端把手多一项「读工作单元 round」——从平台自己的会话记录文件里读(adapters/)。"""
from __future__ import annotations

from pathlib import Path

from tmuxd import Tmuxd

from memorytalk.backend.models.work import Round
from memorytalk.backend.models.work_server import HandleInfo

from .adapters import TranscriptAdapter
from .terminal import TmuxHandle


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

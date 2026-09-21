"""codex:// —— Codex CLI:终端 + 读 ~/.codex/sessions 的 rollout 记录。"""
from __future__ import annotations

from pathlib import Path

from tmuxd import Tmuxd

from memorytalk.backend.models.work_server import Live, ParsedUri, WorkServerInfo, Window
from memorytalk.backend.services.work_servers.adapters import CodexAdapter
from memorytalk.backend.services.work_servers.agent import AgentHandle
from memorytalk.backend.services.work_servers.terminal import kill_session, open_session, resolve_command, session_window


class CodexServer:
    name = "codex"
    protocols = ["codex"]
    description = "Codex:tmux 现场 + 读 ~/.codex/sessions 会话记录"

    def __init__(self, tmuxd: Tmuxd, workspace: Path, adapter: CodexAdapter) -> None:
        self.tmuxd = tmuxd                      # 进程里那一份 tmuxd,启动时注入
        self.workspace = workspace
        self.adapter = adapter                  # 读 Codex 会话记录 → round

    def info(self) -> WorkServerInfo:
        return WorkServerInfo(name=self.name, protocols=self.protocols, description=self.description)

    def open(self, worklet_id: str, uri: ParsedUri, since_mtime: float = 0.0) -> tuple[Live, AgentHandle]:
        cwd, argv = resolve_command(uri, self.workspace, self.name)
        session = open_session(self.tmuxd, worklet_id, cwd, argv)          # tmuxd.session(id, cwd, cmd):有就取回,没有就建
        handle = self.handle(worklet_id, uri, cwd, since_mtime)
        return Live(worklet_id=worklet_id, server=self.name, window=Window(url=session.url, embed=session.url),
                    handle=handle.info(), cwd=str(cwd), command=argv), handle

    def handle(self, worklet_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> AgentHandle:
        return AgentHandle(self.tmuxd, worklet_id, self.adapter, cwd, since_mtime)

    def alive(self, worklet_id: str) -> bool:
        return self.tmuxd.has(worklet_id)

    def window(self, worklet_id: str, uri: ParsedUri) -> Window:
        return session_window(self.tmuxd, worklet_id)

    def destroy(self, worklet_id: str) -> None:
        kill_session(self.tmuxd, worklet_id)


def make(ctx):
    return CodexServer(ctx.tmuxd, ctx.workspace, CodexAdapter(ctx.rt.codex_sessions))

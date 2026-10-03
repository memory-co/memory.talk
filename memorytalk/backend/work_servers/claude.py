"""claude:// —— Claude Code:终端现场;它的 output 由节点推进 trace(work-node.md)。

开的时候把身份定下来(work-node.md §5):新起一个 claude 就发一个会话 id(`--session-id`),会话记录就是
`<projects>/*/<会话 id>.jsonl`,不用按目录和修改时间去猜;再用 `--settings` 注入 hooks,把会话开始 / 一轮的起止 /
等人确认这些事件追加到节点目录里这个工作单元的 hooks.jsonl。取回还活着的现场时不重新起,也就不换会话 id。
"""
from __future__ import annotations

import uuid
from pathlib import Path

from tmuxd import Tmuxd

from memorytalk.backend.models.work_server import HandleInfo, Live, ParsedUri, WorkServerInfo, Window
from memorytalk.backend.services.work_servers.terminal import (TmuxHandle, kill_session, open_session, resolve_command,
                                                              session_window)
from memorytalk.node import layout


class ClaudeHandle(TmuxHandle):
    def info(self) -> HandleInfo:
        return HandleInfo(kind="tmux+transcript", capabilities=["input.text", "input.keys", "trace.agent"])


class ClaudeServer:
    name = "claude"
    protocols = ["claude"]
    description = "Claude Code:tmux 现场;会话记录和 hooks 由节点读了推进 trace"

    def __init__(self, tmuxd: Tmuxd, workspace: Path, projects: Path, node_dir: Path) -> None:
        self.tmuxd = tmuxd                      # 进程里那一份 tmuxd,启动时注入
        self.workspace = workspace
        self.projects = projects                # Claude Code 会话记录根(~/.claude/projects)
        self.node_dir = node_dir                # 节点的状态目录:hooks 事件写到这下面

    def info(self) -> WorkServerInfo:
        return WorkServerInfo(name=self.name, protocols=self.protocols, description=self.description)

    def open(self, worklet_id: str, uri: ParsedUri, since_mtime: float = 0.0) -> tuple[Live, ClaudeHandle]:
        cwd, argv = resolve_command(uri, self.workspace, self.name)
        session_id = None
        if not self.tmuxd.has(worklet_id):                                   # 新起一个:钉住会话 id、注入 hooks
            session_id = str(uuid.uuid4())
            argv = [*argv, "--session-id", session_id, "--settings", str(layout.claude_settings(self.node_dir, worklet_id))]
        session = open_session(self.tmuxd, worklet_id, cwd, argv)          # tmuxd.session(id, cwd, cmd):有就取回,没有就建
        handle = self.handle(worklet_id, uri, cwd, since_mtime)
        return Live(worklet_id=worklet_id, server=self.name, window=Window(url=session.url, embed=session.url),
                    handle=handle.info(), cwd=str(cwd), command=argv, session_id=session_id), handle

    def handle(self, worklet_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> ClaudeHandle:
        return ClaudeHandle(self.tmuxd, worklet_id)

    def watch_spec(self, worklet_id: str, uri: ParsedUri | None = None) -> dict:
        """节点盯这个工作单元要知道的:hooks 事件文件、会话记录根、tmux socket(看现场活没活着)。"""
        return {"hooks": str(layout.hooks_file(self.node_dir, worklet_id)), "transcripts": str(self.projects),
                "tmux_socket": self.tmuxd.tmux_socket}

    def alive(self, worklet_id: str) -> bool:
        return self.tmuxd.has(worklet_id)

    def window(self, worklet_id: str, uri: ParsedUri) -> Window:
        return session_window(self.tmuxd, worklet_id)

    def destroy(self, worklet_id: str) -> None:
        kill_session(self.tmuxd, worklet_id)


def make(ctx):
    return ClaudeServer(ctx.tmuxd, ctx.workspace, ctx.rt.claude_projects, ctx.rt.node_dir)

"""每个协议一个 server,一个文件(docs/works/v5/protocol-server.md)。

load(rt) 返回 (显式认领的, 按约定兜底的) 两组,注册表按「名单优先于约定」解析。
新加一个协议 = 加一个文件 + 在这里排进去。
"""
from __future__ import annotations

from config import RuntimeConfig
from services.servers.terminal import Tmux

from .bash import BashServer
from .claude import ClaudeServer
from .codex import CodexServer
from .http import HttpServer
from .kimi import KimiServer


def load(rt: RuntimeConfig) -> tuple[list, list]:
    tmux = Tmux(rt.tmux_socket)
    term = (tmux, rt.workspace, rt.ttyd_url)
    explicit = [ClaudeServer(*term, rt), CodexServer(*term, rt), KimiServer(*term, rt), HttpServer()]
    fallback = [BashServer(*term)]
    return explicit, fallback


__all__ = ["load", "BashServer", "ClaudeServer", "CodexServer", "KimiServer", "HttpServer"]

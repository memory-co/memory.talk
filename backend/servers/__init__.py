"""每个协议一个 server,一个文件;**server 名 = 协议名(`://` 前面那个)**。

URI 里已经写明了要请求谁,所以没有"认领"、没有兜底:`codex://` 找 codex,`vim://` 没有 vim.py 就是没有。
load(rt) 扫描本包下所有模块,每个模块导出一个 `make(ctx) -> server`,server.name 必须等于文件名。
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path

from config import RuntimeConfig
from services.servers.terminal import Tmux


@dataclass(frozen=True)
class Context:
    rt: RuntimeConfig
    tmux: Tmux
    workspace: Path
    ttyd_url: str | None


def load(rt: RuntimeConfig) -> dict[str, object]:
    ctx = Context(rt=rt, tmux=Tmux(rt.tmux_socket), workspace=rt.workspace, ttyd_url=rt.ttyd_url)
    servers: dict[str, object] = {}
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{mod.name}")
        server = module.make(ctx)
        assert server.name == mod.name, f"servers/{mod.name}.py 的 server.name 必须是 {mod.name!r}"
        servers[server.name] = server
    return servers


__all__ = ["load", "Context"]

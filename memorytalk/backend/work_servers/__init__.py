"""每个 server 一个文件。**server 自己声明它响应哪些协议**(`protocols`),一个 server 可以响应多个
(http.py 同时接 http 和 https);没有任何 server 声明的协议,一律去 **default**(背后是 bash,把协议名当命令跑)。

load(rt) 扫描本包下所有模块,每个模块导出 `make(ctx) -> server`。
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path

from memorytalk.backend.config import RuntimeConfig
from tmuxd import Tmuxd

DEFAULT = "default"


@dataclass(frozen=True)
class Context:
    rt: RuntimeConfig
    tmuxd: Tmuxd               # 终端类 server 的实现面:一个进程一份(自己的 socket / ttyd / state)
    workspace: Path


def load(rt: RuntimeConfig, tmuxd: Tmuxd) -> list[object]:
    ctx = Context(rt=rt, tmuxd=tmuxd, workspace=rt.workspace)
    servers = []
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        servers.append(importlib.import_module(f"{__name__}.{mod.name}").make(ctx))
    # default 排最后:先查显式声明,再兜底
    servers.sort(key=lambda s: s.name == DEFAULT)
    return servers


__all__ = ["load", "Context", "DEFAULT"]

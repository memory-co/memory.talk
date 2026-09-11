"""memory.talk 命令行:本地 API 的客户端,不含业务逻辑(docs/cli/v5)。

    memory.talk server      start | stop | restart | status | daemon        → cli/server.py
    memory.talk work        create | list | show | set | attach | …          → cli/work.py
    memory.talk user        add | list | show | set | whoami                 → cli/user.py
    memory.talk collection  layers | tree | ls | recall | search | read | … → cli/collection.py(别名 col)

每个子命令组一个文件,各自 register(top) 挂到总 parser 上;公共件在 _common.py。
"""
from __future__ import annotations

import argparse
import os

from . import collection, server, user, work
from ._common import DEFAULT_SERVER, Api


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="memory.talk", description="memory.talk v5 —— 跑 code agent 的工作台,记忆是它的副产物")
    ap.add_argument("--server", default=os.environ.get("MEMORY_TALK_SERVER", DEFAULT_SERVER), help="API 在哪")
    ap.add_argument("--user", default=os.environ.get("MEMORY_TALK_USER"), help="我是谁(须注册过)")
    ap.add_argument("--work", default=os.environ.get("MEMORY_TALK_WORK"), help="在哪个 work 里操作")
    ap.add_argument("--json", action="store_true", help="结构化输出")
    top = ap.add_subparsers(dest="cmd", required=True)
    for group in (server, work, user, collection):
        group.register(top)
    return ap


def main(argv: list[str] | None = None) -> None:
    a = build_parser().parse_args(argv)
    if getattr(a, "local", None):          # server 组:本地动作,不经 API
        a.local(a)
        return
    a.fn(Api(a.server, a.user, a.work), a)


__all__ = ["main", "build_parser"]

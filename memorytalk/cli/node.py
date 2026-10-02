"""memory.talk node —— 本机节点的生命周期:start / stop / status / daemon(docs/designs/v5/work-node.md)。

节点不是中心的子进程:重启中心不动它(agent 照跑、记录照读,中心回来了接着推);`server start` 顺手把它起来,
`server stop` 连它一起停。
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

from ._common import Fail


def _node_dir() -> Path:
    from memorytalk.backend.config import load_runtime_config
    return load_runtime_config().node_dir


def _instance_path() -> Path:
    return _node_dir() / "node.json"


def _read_instance() -> dict | None:
    try:
        return json.loads(_instance_path().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _health() -> dict | None:
    sock = _node_dir() / "node.sock"
    if not sock.exists():
        return None
    try:
        with httpx.Client(transport=httpx.HTTPTransport(uds=str(sock)), base_url="http://node", timeout=2) as c:
            return c.get("/health").json()
    except (httpx.HTTPError, OSError, ValueError):
        return None


def running() -> dict | None:
    inst = _read_instance()
    return inst if inst and _alive(inst["pid"]) and _health() else None


def node_daemon(a) -> None:
    from memorytalk.backend.config import load_runtime_config
    from memorytalk.node.daemon import run
    rt = load_runtime_config()
    run(rt.node_dir, rt.center_socket)


def node_start(a=None, *, quiet: bool = False) -> None:
    if inst := running():
        if not quiet:
            print(f"节点已在跑(pid {inst['pid']})")
        return
    d = _node_dir()
    d.mkdir(parents=True, exist_ok=True)
    log = open(d / "node.log", "ab")
    proc = subprocess.Popen([sys.executable, "-m", "memorytalk", "node", "daemon"], stdout=log, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, start_new_session=True)
    _instance_path().write_text(json.dumps({"pid": proc.pid, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
    for _ in range(50):
        if _health():
            break
        if proc.poll() is not None:
            tail = (d / "node.log").read_text(errors="replace").splitlines()[-15:]
            raise Fail("节点起不来:\n" + "\n".join(tail), 1)
        time.sleep(0.2)
    else:
        raise Fail("节点 10 秒内没就绪,看 " + str(d / "node.log"), 1)
    if not quiet:
        print(f"节点已启动(pid {proc.pid})\n  目录    {d}\n  日志    {d / 'node.log'}\n  停止    memory.talk node stop")


def node_stop(a, quiet: bool = False) -> None:
    inst = _read_instance()
    if not inst or not _alive(inst["pid"]):
        if not quiet:
            print("节点没在跑")
        return
    os.kill(inst["pid"], signal.SIGTERM)
    for _ in range(25):
        if not _alive(inst["pid"]):
            break
        time.sleep(0.2)
    else:
        os.kill(inst["pid"], signal.SIGKILL)
    print(f"节点已停止(pid {inst['pid']})。盯着的工作单元记在 {_node_dir() / 'worklets'},下次起来接着盯")


def node_status(a) -> None:
    inst = _read_instance()
    health = _health() if inst and _alive(inst["pid"]) else None
    if a.json:
        print(json.dumps({**(inst or {}), "running": bool(health), **(health or {})}, indent=2))
    elif not health:
        print("节点没在跑")
    else:
        print(f"节点运行中(pid {inst['pid']})\n  目录     {_node_dir()}\n  在盯     {health['watching']} 个工作单元\n"
              f"  启动于   {inst['started_at']}")
    if not health:
        raise SystemExit(1)


def register(top) -> None:
    s = top.add_parser("node", help="本机节点:读 agent 的会话记录和 hooks,推进 trace").add_subparsers(dest="sub", required=True)
    for name, fn in (("start", node_start), ("daemon", node_daemon), ("stop", node_stop), ("status", node_status)):
        s.add_parser(name).set_defaults(local=fn)

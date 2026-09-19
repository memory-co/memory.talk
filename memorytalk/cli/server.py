"""memory.talk server —— 本地 API 服务的生命周期:start / stop / restart / status / daemon(照 shellbase)。"""
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



def _home() -> Path:
    return Path(os.environ.get("MEMORY_TALK_HOME", "~/.memory.talk")).expanduser()


def _instance_path() -> Path:
    return _home() / "instance.json"


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


def _health(url: str) -> bool:
    try:
        return httpx.get(f"{url}/api/system/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def server_start(a) -> None:
    inst = _read_instance()
    if inst and _alive(inst["pid"]) and _health(inst["url"]):
        print(f"memory.talk 已在跑(pid {inst['pid']}) {inst['url']}")
        return
    home = _home()
    home.mkdir(parents=True, exist_ok=True)
    log = open(home / "server.log", "ab")
    cmd = [sys.executable, "-m", "memorytalk", "server", "daemon", "--host", a.host, "--port", str(a.port)]
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            start_new_session=True, env={**os.environ, "MEMORY_TALK_HOME": str(home)})
    url = f"http://{a.host}:{a.port}"
    inst = {"pid": proc.pid, "url": url, "host": a.host, "port": a.port, "home": str(home),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "store": os.environ.get("MEMORY_TALK_STORE", "fs")}
    _instance_path().write_text(json.dumps(inst, indent=2))
    for _ in range(50):
        if _health(url):
            break
        if proc.poll() is not None:
            tail = (home / "server.log").read_text(errors="replace").splitlines()[-15:]
            raise Fail("起不来:\n" + "\n".join(tail), 1)
        time.sleep(0.2)
    else:
        raise Fail("10 秒内没就绪,看 " + str(home / "server.log"), 1)
    print(f"memory.talk 已启动(pid {proc.pid})\n  地址    {url}\n  文档    {url}/docs\n  存储    {inst['store']}  {home}\n"
          f"  日志    {home / 'server.log'}\n  停止    memory.talk server stop")


def server_stop(a) -> None:
    inst = _read_instance()
    if not inst or not _alive(inst["pid"]):
        print("memory.talk 没在跑")
        return
    os.kill(inst["pid"], signal.SIGTERM)
    for _ in range(25):
        if not _alive(inst["pid"]):
            break
        time.sleep(0.2)
    else:
        os.kill(inst["pid"], signal.SIGKILL)
    print(f"memory.talk 已停止(pid {inst['pid']})。tmux 会话不动,下次 start 后按登记重入")


def server_restart(a) -> None:
    inst = _read_instance() or {}
    server_stop(a)
    a.host = inst.get("host", a.host)
    a.port = inst.get("port", a.port)
    server_start(a)


def server_status(a) -> None:
    inst = _read_instance()
    ok = bool(inst and _alive(inst["pid"]) and _health(inst["url"]))
    if a.json:
        print(json.dumps({**(inst or {}), "running": ok}, indent=2))
    elif not ok:
        print("memory.talk 没在跑" + (f"(instance.json 里有 pid {inst['pid']},但进程或健康检查不通过)" if inst else ""))
    else:
        from .auth import saved_token
        _, token = saved_token(inst["url"], os.environ.get("MEMORY_TALK_USER"))
        r = httpx.get(f"{inst['url']}/api/system/info", timeout=2, headers={"Authorization": f"Bearer {token}"} if token else {})
        body = r.json()
        store = f"{body['data']['store']['backend']}  {body['data']['home']}" if r.status_code == 200 else \
            "(先 memory.talk setup)" if body.get("error") == "setup_required" else "(先 memory.talk login)"
        print(f"memory.talk 运行中(pid {inst['pid']})\n  地址     {inst['url']}\n  存储     {store}\n"
              f"  启动于   {inst['started_at']}\n  健康     ok\n  停止     memory.talk server stop")
    if not ok:
        raise SystemExit(1)


def server_daemon(a) -> None:
    import uvicorn
    uvicorn.run("memorytalk.backend.main:create_app", factory=True, host=a.host, port=a.port, log_level="info")




def register(top) -> None:
    s = top.add_parser("server", help="本地 API 服务").add_subparsers(dest="sub", required=True)
    for name, fn in (("start", server_start), ("daemon", server_daemon), ("restart", server_restart)):
        p = s.add_parser(name)
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8000)
        p.set_defaults(local=fn)
    s.add_parser("stop").set_defaults(local=server_stop)
    s.add_parser("status").set_defaults(local=server_status)

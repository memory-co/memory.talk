"""节点进程:`memory.talk node daemon`。

    中心 → 节点:<node 目录>/node.sock(watch / flush / list,一个很小的 HTTP 口子)
    节点 → 中心:<home>/center.sock(就是中心的 API;从这个 socket 上来的请求身份是节点,只能读写 trace)

两个 socket 都是 0600、属于跑服务的那个用户:同一台机器上靠文件权限,不发 token(work-node.md §8)。
后台一个线程每隔 INTERVAL 轮一遍盯着的工作单元。
"""
from __future__ import annotations

import logging
import os
import socket
import threading
from pathlib import Path

import httpx

from .node import Node, Rejected, Unreachable

INTERVAL = 0.5                 # 秒;只 stat,变了才读

log = logging.getLogger(__name__)


class HttpCenter:
    """经中心的 unix socket 推 trace、问游标(POST / GET /api/works/{id}/trace,和读同一个接口)。"""

    def __init__(self, center_socket: Path, timeout: float = 30.0) -> None:
        self.client = httpx.Client(transport=httpx.HTTPTransport(uds=str(center_socket)), base_url="http://center",
                                   timeout=timeout)

    def _send(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            return self.client.request(method, path, **kw)
        except httpx.TransportError as e:              # socket 不在 / 拒绝连接 / 超时:中心没起来或正在重启
            raise Unreachable(str(e) or type(e).__name__) from e

    def push(self, work_id: str, body: dict) -> dict:
        r = self._send("POST", f"/api/works/{work_id}/trace", json=body)
        if 400 <= r.status_code < 500:
            raise Rejected(f"{r.status_code} {r.text[:300]}")
        r.raise_for_status()
        return r.json().get("data") or {}

    def cursors(self, work_id: str, worklet_id: str) -> list[dict]:
        r = self._send("GET", f"/api/works/{work_id}/trace", params={"worklet": worklet_id, "fields": "cursors"})
        if r.status_code == 404:                       # work 没了:从头读(推上去也会被拒)
            return []
        r.raise_for_status()
        return (r.json().get("data") or {}).get("cursors") or []


def control_app(node: Node):
    """中心说话的口子。处理函数是同步的,Starlette 放到线程池里跑(flush 要等读完推完)。"""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def body(request: Request) -> dict:
        try:
            return await request.json()
        except ValueError:
            return {}

    async def watch(request: Request):
        from starlette.concurrency import run_in_threadpool
        spec = await body(request)
        try:
            return JSONResponse(await run_in_threadpool(node.watch, spec))
        except (ValueError, TypeError, KeyError) as e:
            return JSONResponse({"error": str(e)}, status_code=422)

    async def flush(request: Request):
        from starlette.concurrency import run_in_threadpool
        d = await body(request)
        return JSONResponse(await run_in_threadpool(node.flush, str(d.get("worklet_id", "")), str(d.get("reason", "detached"))))

    def listing(request: Request):
        return JSONResponse(node.list())

    def health(request: Request):
        return JSONResponse({"ok": True, "pid": os.getpid(), "watching": len(node.watching)})

    return Starlette(routes=[Route("/watch", watch, methods=["POST"]), Route("/flush", flush, methods=["POST"]),
                             Route("/list", listing), Route("/health", health)])


def bind_unix(path: Path) -> socket.socket:
    """0600 的 unix socket:只有跑服务的那个用户连得上(uvicorn 自己的 uds= 会 chmod 成 0666,所以自己绑)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)
    try:
        sock.bind(str(path))
    finally:
        os.umask(old)
    os.chmod(path, 0o600)
    sock.listen(128)
    return sock


def run(node_dir: Path, center_socket: Path) -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    node = Node(node_dir, HttpCenter(center_socket))
    node.load()
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(INTERVAL):
            node.poll()

    poller = threading.Thread(target=loop, name="node-poll", daemon=True)
    poller.start()
    path = Path(node_dir) / "node.sock"
    sock = bind_unix(path)
    log.info("节点起来了:%s → %s,接着盯 %d 个工作单元", path, center_socket, len(node.watching))
    try:
        uvicorn.Server(uvicorn.Config(control_app(node), lifespan="off", log_level="warning")).run(sockets=[sock])
    finally:
        stop.set()
        poller.join(timeout=10)
        path.unlink(missing_ok=True)

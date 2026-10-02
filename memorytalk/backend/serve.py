"""起中心:同一个 app 听两个口子(memory.talk server daemon)。

    TCP <host>:<port>       人和浏览器(门:JWT / 窗的 cookie)
    <home>/center.sock      节点(0600;从这里上来的请求身份就是节点,只能读写 trace,work-node.md §6)

两个 uvicorn Server 跑在一个事件循环里;信号自己接,一起停(uvicorn 自己接信号的话,停完会把信号再抛一次,
后面收尾的代码就跑不到了)。lifespan(起停 tmuxd 的 ttyd、清 viewers)只在 TCP 那个上跑一次。
"""
from __future__ import annotations

import asyncio
import contextlib
import signal

import uvicorn

from memorytalk.node.daemon import bind_unix

from .gateway import NodeSocket
from .main import create_app


class _Server(uvicorn.Server):
    def capture_signals(self):                   # 信号由 _serve 统一接
        return contextlib.nullcontext()


def serve(host: str, port: int) -> None:
    asyncio.run(_serve(host, port))


async def _serve(host: str, port: int) -> None:
    app = create_app()
    path = app.state.runtime.center_socket
    main = _Server(uvicorn.Config(app, host=host, port=port, log_level="info"))
    side = _Server(uvicorn.Config(NodeSocket(app), lifespan="off", log_level="warning"))
    sock = bind_unix(path)

    def stop() -> None:
        main.should_exit = side.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop)
    try:
        await asyncio.gather(main.serve(), side.serve(sockets=[sock]))
    finally:
        path.unlink(missing_ok=True)

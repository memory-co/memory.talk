"""起中心:同一个 app 听两个口子(memory.talk server daemon)。

    TCP <host>:<port>       人和浏览器(门:JWT / 窗的 cookie)
    <home>/center.sock      节点(0600;从这里上来的请求身份就是节点,只能读写 trace,work-node.md §6)

两个 uvicorn Server 跑在一个事件循环里;信号自己接,一起停(uvicorn 自己接信号的话,停完会把信号再抛一次,
后面收尾的代码就跑不到了)。lifespan(起停 tmuxd 的 ttyd、清 viewers)只在 TCP 那个上跑一次。
日志配置是全局的:只让 TCP 那个配(节点那个再配一次会把级别改掉);节点推的请求不进访问日志。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

import uvicorn

from memorytalk.node.daemon import bind_unix

from .gateway import NodeSocket
from .main import create_app


class _Server(uvicorn.Server):
    def capture_signals(self):                   # 信号由 _serve 统一接
        return contextlib.nullcontext()


class _NodeAccess(logging.Filter):
    """从 unix socket 上来的(没有客户端地址,就是节点在推)不记访问日志:一个 agent 干活时一秒一两条,会把别的淹掉。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return not (isinstance(record.args, tuple) and record.args and record.args[0] == "")


def serve(host: str, port: int) -> None:
    asyncio.run(_serve(host, port))


async def _serve(host: str, port: int) -> None:
    app = create_app()
    path = app.state.runtime.center_socket
    main = _Server(uvicorn.Config(app, host=host, port=port, log_level="info"))
    side = _Server(uvicorn.Config(NodeSocket(app), lifespan="off", log_config=None, log_level=None))
    logging.getLogger("uvicorn.access").addFilter(_NodeAccess())
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

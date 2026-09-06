"""http:// https:// —— 浏览器块,一个 server 响应两个协议。现在最薄:窗 = URL 本身,把手为空(状态不撒谎)。
本地服务(localhost:port)的 embed 走 /proxy/<port>/;换成 webmuxd 后协议不变。"""
from __future__ import annotations

from pathlib import Path

from models.server import HandleInfo, Live, ParsedUri, ServerInfo, Window


class NoHandle:
    def info(self) -> HandleInfo:
        return HandleInfo(kind="none", capabilities=[])

    def alive(self) -> bool:
        return True


class HttpServer:
    name = "http"
    protocols = ["http", "https"]
    description = "网页块:外链直嵌,本地服务经网关代理;把手为空"

    def info(self) -> ServerInfo:
        return ServerInfo(name=self.name, protocols=self.protocols, description=self.description)

    def open(self, session_id: str, uri: ParsedUri, since_mtime: float = 0.0) -> tuple[Live, NoHandle]:
        local = uri.host in ("localhost", "127.0.0.1")
        embed = f"/proxy/{uri.port}{uri.path or '/'}" if local and uri.port else uri.raw
        h = NoHandle()
        return Live(session_id=session_id, server=self.name, window=Window(url=uri.raw, embed=embed),
                    handle=h.info()), h

    def handle(self, session_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> NoHandle:
        return NoHandle()

    def alive(self, session_id: str) -> bool:
        return True

    def destroy(self, session_id: str) -> None:
        pass


def make(ctx):
    return HttpServer()

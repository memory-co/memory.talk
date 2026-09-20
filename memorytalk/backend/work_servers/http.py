"""http:// https:// —— 浏览器块,一个 server 响应两个协议。现在最薄:窗 = URL 本身,把手为空(状态不撒谎)。
本地服务(localhost:port)的 embed 走 /proxy/<port>/;换成 webmuxd 后协议不变。"""
from __future__ import annotations

from pathlib import Path

from memorytalk.backend.models.work_server import HandleInfo, Live, ParsedUri, WorkServerInfo, Window


class NoHandle:
    def info(self) -> HandleInfo:
        return HandleInfo(kind="none", capabilities=[])

    def alive(self) -> bool:
        return True


class HttpServer:
    name = "http"
    protocols = ["http", "https"]
    description = "网页块:外链直嵌,本地服务经网关代理;把手为空"

    def info(self) -> WorkServerInfo:
        return WorkServerInfo(name=self.name, protocols=self.protocols, description=self.description)

    def window(self, worklet_id: str, uri: ParsedUri) -> Window:
        local = uri.host in ("localhost", "127.0.0.1")
        embed = f"/proxy/{uri.port}{uri.path or '/'}" if local and uri.port else uri.raw
        return Window(url=uri.raw, embed=embed)

    def open(self, worklet_id: str, uri: ParsedUri, since_mtime: float = 0.0) -> tuple[Live, NoHandle]:
        h = NoHandle()
        return Live(worklet_id=worklet_id, server=self.name, window=self.window(worklet_id, uri), handle=h.info()), h

    def handle(self, worklet_id: str, uri: ParsedUri, cwd: Path, since_mtime: float) -> NoHandle:
        return NoHandle()

    def alive(self, worklet_id: str) -> bool:
        return True

    def destroy(self, worklet_id: str) -> None:
        pass


def make(ctx):
    return HttpServer()

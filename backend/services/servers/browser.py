"""浏览器 server:https:// http:// —— 现在最薄:窗 = URL 本身,把手为空(状态不撒谎)。"""
from __future__ import annotations

from models.server import HandleInfo, Live, ParsedUri, ServerInfo, Window


class NoHandle:
    def info(self) -> HandleInfo:
        return HandleInfo(kind="none", capabilities=[])

    def alive(self) -> bool:
        return True


class BrowserServer:
    name = "browser"
    description = "外链直嵌;本地服务将来经网关代理;换成 webmuxd 后协议不变"

    def info(self) -> ServerInfo:
        return ServerInfo(name=self.name, claims=["http", "https"], description=self.description)

    def claims(self, scheme: str) -> bool:
        return scheme in ("http", "https")

    def open(self, member_id: str, uri: ParsedUri) -> tuple[Live, NoHandle]:
        local = uri.host in ("localhost", "127.0.0.1")
        embed = f"/proxy/{uri.port}{uri.path or '/'}" if local and uri.port else uri.raw
        h = NoHandle()
        return Live(member_id=member_id, server=self.name, window=Window(url=uri.raw, embed=embed),
                    handle=h.info()), h

    def alive(self, member_id: str) -> bool:
        return True

    def destroy(self, member_id: str) -> None:
        pass

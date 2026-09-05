"""文件 server:file:// —— 窗 = 文件浏览器页面;把手先为空(文件 API 随前端一起做)。"""
from __future__ import annotations

from urllib.parse import quote

from models.server import HandleInfo, Live, ParsedUri, ServerInfo, Window

from .browser import NoHandle


class FilesServer:
    name = "files"
    description = "file:// → /apps/files?path=…"

    def info(self) -> ServerInfo:
        return ServerInfo(name=self.name, claims=["file"], description=self.description)

    def claims(self, scheme: str) -> bool:
        return scheme == "file"

    def open(self, member_id: str, uri: ParsedUri) -> tuple[Live, NoHandle]:
        embed = f"/apps/files?path={quote(uri.path or '/')}"
        h = NoHandle()
        return Live(member_id=member_id, server=self.name, window=Window(url=embed, embed=embed),
                    handle=h.info(), cwd=uri.path or None), h

    def alive(self, member_id: str) -> bool:
        return True

    def destroy(self, member_id: str) -> None:
        pass

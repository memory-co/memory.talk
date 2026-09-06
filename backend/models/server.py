"""server —— 认领协议、幂等建现场、交回窗 + 把手(docs/works/v5/protocol-server.md)。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ParsedUri(BaseModel):
    raw: str
    scheme: str
    path: str = ""                 # 终端类:工作目录(或文件);file:// 路径;https:// 无意义
    host: str = ""                 # https 类:host
    port: int | None = None
    query: dict[str, str] = Field(default_factory=dict)


class Window(BaseModel):
    """人能直接打开的那扇窗。url 为 None = 这个现场没有画面(状态不撒谎)。"""
    url: str | None = None
    embed: str | None = Field(None, description="画布 iframe 该装什么(与 url 可不同,如本地服务经代理)")


class HandleInfo(BaseModel):
    """把手长什么样(给 API 报出来的描述;真正的把手是 Python 对象)。"""
    kind: str                                   # tmux / none / files
    capabilities: list[str] = Field(default_factory=list)   # capture / send / rounds / …


class Live(BaseModel):
    """一次 open 的结果:现场活着,这是看它、驱动它的两样东西。"""
    member_id: str
    server: str
    window: Window
    handle: HandleInfo
    cwd: str | None = None
    command: list[str] | None = None


class ServerInfo(BaseModel):
    name: str = Field(description="= 协议名(URI 里 :// 前面那个)")
    description: str = ""


@runtime_checkable
class Handle(Protocol):
    def info(self) -> HandleInfo: ...
    def alive(self) -> bool: ...


class ServerError(RuntimeError):
    """server 侧的失败,必须说清楚(M12):code 指向不同的下一步。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

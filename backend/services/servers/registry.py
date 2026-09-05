"""协议 → server:名单优先于约定,具体优先于兜底;找不到明确报错,不静默兜底。"""
from __future__ import annotations

from models.server import ParsedUri, ServerError, ServerInfo


class Registry:
    def __init__(self, explicit: list, fallback: list) -> None:
        self.explicit, self.fallback = explicit, fallback

    def resolve(self, uri: ParsedUri):
        for s in self.explicit:
            if s.claims(uri.scheme):
                return s
        for s in self.fallback:
            if s.claims(uri.scheme):
                return s
        raise ServerError("no_server", f"没有 server 认领 {uri.scheme}://;PATH 里也没有叫 {uri.scheme!r} 的命令")

    def by_name(self, name: str):
        for s in [*self.explicit, *self.fallback]:
            if s.name == name:
                return s
        raise ServerError("no_server", f"没有叫 {name!r} 的 server")

    def infos(self) -> list[ServerInfo]:
        return [s.info() for s in [*self.explicit, *self.fallback]]

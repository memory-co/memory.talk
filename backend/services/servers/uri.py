"""块的 URI 解析:scheme:///path?query。终端类 path = 工作目录;https 类看 host。"""
from __future__ import annotations

from urllib.parse import parse_qsl, unquote, urlsplit

from models.server import ParsedUri, ServerError


def parse_uri(raw: str) -> ParsedUri:
    s = urlsplit(raw)
    if not s.scheme:
        raise ServerError("bad_uri", f"URI 没有协议: {raw!r}")
    return ParsedUri(
        raw=raw, scheme=s.scheme.lower(), path=unquote(s.path or ""),
        host=s.hostname or "", port=s.port,
        query=dict(parse_qsl(s.query, keep_blank_values=True)),
    )

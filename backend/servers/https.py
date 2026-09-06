"""https:// —— 同 http,只是协议名不同(server 名 = 协议名,所以单独一个文件)。"""
from __future__ import annotations

from .http import HttpServer


class HttpsServer(HttpServer):
    name = "https"


def make(ctx):
    return HttpsServer()

"""统一响应信封:所有 /api/* 的响应都是 {"data": …, "message": …};出错时多一个 "error"(机器码)。

- JSON 响应 → data = 原来的 body;
- 纯文本响应(recall / capture)→ data = 那段文本;
- 204 → 200,data = null;
- 已经是信封的(错误处理器直接产出的)原样放行;/docs /openapi.json 不碰。
"""
from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def envelope(data, message: str = "ok", error: str | None = None) -> dict:
    body = {"data": data, "message": message}
    if error:
        body["error"] = error
    return body


def is_envelope(obj) -> bool:
    return isinstance(obj, dict) and "data" in obj and "message" in obj and set(obj) <= {"data", "message", "error"}


class EnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            return response
        raw = b"".join([chunk async for chunk in response.body_iterator])
        ctype = response.headers.get("content-type", "")
        status = 200 if response.status_code == 204 else response.status_code
        if status == 204 or not raw:
            payload = envelope(None)
        elif ctype.startswith("application/json"):
            obj = json.loads(raw)
            payload = obj if is_envelope(obj) else envelope(obj)
        else:
            payload = envelope(raw.decode("utf-8", "replace"))
        headers = {k: v for k, v in response.headers.items() if k.lower() not in ("content-length", "content-type")}
        return JSONResponse(payload, status_code=status, headers=headers)

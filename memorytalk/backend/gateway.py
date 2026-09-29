"""入口:前端构建产物的静态托管(页面用 hash 路由，API 保留独立的路径空间),和门(AuthMiddleware)。"""
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from memorytalk.backend.models.result import fail


def mount_frontend(app: FastAPI, directory: Path | None = None) -> None:
    root = directory if directory is not None else Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if not (root / "index.html").is_file():
        return

    @app.get("/", include_in_schema=False)
    def frontend():
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="frontend-assets")


# ---- 门:一个纯 ASGI 中间件,包住整个 app(docs/designs/v5/auth.md §5) ----

OPEN = {"/api/auth/status", "/api/auth/setup", "/api/auth/login", "/api/system/health"}
SURFACE_PATH = "/surface"          # 窗(surface)都挂在这下面:/surface/tmuxd(终端),以后 /surface/webmuxd(浏览器)……
SURFACE_COOKIE = "mt_surface"      # 窗的门:iframe / WebSocket 带不了头,凭它进;Path=/surface


class AuthMiddleware:
    """门:纯 ASGI,包在最外层——/api 路由和挂在 /surface 下的窗(子 app)、HTTP 和 WebSocket 都先过这里,子 app 自己不再设门。

    凭证按路径定,不互相回退:
      /api/*(OPEN 以外)  只认 Authorization: Bearer <JWT>。不认 cookie:浏览器会自动带 cookie,认了就有 CSRF。
      /surface/*          只认 mt_surface cookie(iframe / WebSocket 带不了头);WebSocket 另验 Origin 同源(防跨站劫持)。
      其余(前端、OPEN)  放行。
    没有 admin → /api 409 setup_required、/surface 一律拒;过了门,名字放进 scope["state"]["user"](FastAPI 里是 request.state.user)。
    """

    def __init__(self, app, auth) -> None:
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path = scope["path"]
        if path.startswith("/api") and path not in OPEN:
            kind = "api"
        elif path == SURFACE_PATH or path.startswith(SURFACE_PATH + "/"):
            kind = "surface"
        else:
            return await self.app(scope, receive, send)

        headers = _headers(scope)
        if self.auth.setup_required():
            return await _reject(scope, receive, send, kind, 409, "setup_required", "还没有 admin 账号,先 POST /api/auth/setup")
        if kind == "api":
            value = headers.get("authorization", "")
            token = value[7:].strip() if value.lower().startswith("bearer ") else None
        else:
            morsel = SimpleCookie(headers.get("cookie", "")).get(SURFACE_COOKIE)
            token = morsel.value if morsel is not None else None
            if scope["type"] == "websocket" and not _same_origin(headers):
                return await _reject(scope, receive, send, kind, 403, "forbidden", "跨站的 WebSocket")
        name = self.auth.resolve(token)
        if name is None:
            return await _reject(scope, receive, send, kind, 401, "unauthorized", "要登录:Authorization: Bearer <token>")
        scope.setdefault("state", {})["user"] = name
        await self.app(scope, receive, send)


def _headers(scope) -> dict[str, str]:
    """小写名 → 值;同名的(cookie 可能分几行)用 "; " 接起来。"""
    out: dict[str, str] = {}
    for k, v in scope.get("headers", []):
        name, value = k.decode("latin-1").lower(), v.decode("latin-1")
        out[name] = f"{out[name]}; {value}" if name in out else value
    return out


def _same_origin(headers: dict[str, str]) -> bool:
    """没有 Origin(非浏览器客户端)不算跨站;有就得和 Host 一致。"""
    origin = headers.get("origin")
    return origin is None or urlsplit(origin).netloc == headers.get("host")


async def _reject(scope, receive, send, kind: str, status: int, code: str, message: str) -> None:
    if scope["type"] == "websocket":
        await receive()                                         # websocket.connect;不 accept 直接 close = 握手被拒
        await send({"type": "websocket.close", "code": 1008})
    elif kind == "api":
        await JSONResponse(fail(code, message), status_code=status)(scope, receive, send)
    else:
        await PlainTextResponse("forbidden", status_code=403)(scope, receive, send)

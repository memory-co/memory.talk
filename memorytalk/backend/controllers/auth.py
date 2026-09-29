"""/api/auth —— 门:status / setup / login / logout。身份来自 token(docs/designs/v5/auth.md),controller 从 request.state.user 取。
终端窗(/tty,iframe + WebSocket)带不了 Authorization 头:status 顺手把 token 种成只发给 /tty 的 HttpOnly cookie,tty_gate 认它。"""
from __future__ import annotations

from http.cookies import SimpleCookie

from fastapi import APIRouter, Depends, Request, Response

from memorytalk.backend.models.auth import AuthStatus, LoginRequest, LoginResult, SetupRequest
from memorytalk.backend.models.result import Result, ok
from memorytalk.backend.services.auth import ADMIN, AuthError, AuthService
from memorytalk.backend.services.work_servers import TTY_PATH

router = APIRouter(prefix="/api/auth", tags=["auth"])

TTY_COOKIE = "mt_tty"


def _tty_cookie(response: Response, token: str | None) -> None:
    """有效 token → 种进 /tty 的 cookie(和 Bearer 同一个串:logout / 换密码一起作废);没有 → 清掉。"""
    if token:
        response.set_cookie(TTY_COOKIE, token, path=TTY_PATH, httponly=True, samesite="strict")
    else:
        response.delete_cookie(TTY_COOKIE, path=TTY_PATH, httponly=True, samesite="strict")


def tty_gate(svc: AuthService):
    """挂 /tty 的 tmuxd.asgi(authorize=…):页面、/token、/ws、静态资源每一个请求都过这里,凭 cookie 里的 token 放行。"""
    def authorize(scope) -> bool:
        raw = b"; ".join(v for k, v in scope.get("headers", []) if k == b"cookie").decode("latin-1")
        morsel = SimpleCookie(raw).get(TTY_COOKIE) if raw else None
        return morsel is not None and not svc.setup_required() and svc.resolve(morsel.value) is not None
    return authorize


def auth(request: Request) -> AuthService:
    return request.app.state.auth


def bearer(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    return value[7:].strip() if value.lower().startswith("bearer ") else None


def current_user(request: Request) -> str:
    """谁在操作:中间件解析 token 放进来的名字(进了门就一定有)。"""
    return request.state.user


def require_admin(request: Request) -> str:
    name = request.state.user
    if request.app.state.users.get(name).role != "admin":
        raise AuthError("forbidden", "只有 admin 能做这个", 403)
    return name


@router.get("/status", response_model=Result[AuthStatus], summary="门的状态:要不要先 setup;这次带的 token 有效吗、是谁")
def status(request: Request, response: Response, svc: AuthService = Depends(auth)):
    token = bearer(request)
    name = svc.resolve(token)
    _tty_cookie(response, token if name else None)
    return ok(AuthStatus(setup_required=svc.setup_required(), authenticated=name is not None,
                         user=svc.users.get(name) if name else None))


@router.post("/setup", response_model=Result[LoginResult], status_code=201, summary=f"首次:建 {ADMIN} 账号并登录;admin 已存在 → 404")
def setup(req: SetupRequest, svc: AuthService = Depends(auth)):
    return ok(svc.setup(req))


@router.post("/login", response_model=Result[LoginResult], summary="密码换 token;之后 Authorization: Bearer <token>")
def login(req: LoginRequest, svc: AuthService = Depends(auth)):
    return ok(svc.login(req.name, req.password))


@router.post("/logout", response_model=Result[dict], summary="作废这次带的 token")
def logout(request: Request, response: Response, svc: AuthService = Depends(auth)):
    svc.logout(bearer(request))
    _tty_cookie(response, None)
    return ok({})

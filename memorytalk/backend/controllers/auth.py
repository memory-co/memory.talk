"""/api/auth —— 门:status / setup / login / logout。身份来自 token(docs/designs/v5/auth.md),controller 从 request.state.user 取。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from memorytalk.backend.models.auth import AuthStatus, LoginRequest, LoginResult, SetupRequest
from memorytalk.backend.models.result import Result, ok
from memorytalk.backend.services.auth import ADMIN, AuthError, AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
def status(request: Request, svc: AuthService = Depends(auth)):
    name = svc.resolve(bearer(request))
    return ok(AuthStatus(setup_required=svc.setup_required(), authenticated=name is not None,
                         user=svc.users.get(name) if name else None))


@router.post("/setup", response_model=Result[LoginResult], status_code=201, summary=f"首次:建 {ADMIN} 账号并登录;admin 已存在 → 404")
def setup(req: SetupRequest, svc: AuthService = Depends(auth)):
    return ok(svc.setup(req))


@router.post("/login", response_model=Result[LoginResult], summary="密码换 token;之后 Authorization: Bearer <token>")
def login(req: LoginRequest, svc: AuthService = Depends(auth)):
    return ok(svc.login(req.name, req.password))


@router.post("/logout", response_model=Result[dict], summary="作废这次带的 token")
def logout(request: Request, svc: AuthService = Depends(auth)):
    svc.logout(bearer(request))
    return ok({})

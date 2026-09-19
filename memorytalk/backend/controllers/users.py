"""/api/users —— user 是注册的顶层对象:注册(admin)、档案、清单、我是谁、密码。权限只有 admin 管账号这一档。"""
from __future__ import annotations

from memorytalk.backend.models.result import Result, ok
from fastapi import APIRouter, Depends, Request

from memorytalk.backend.controllers.auth import current_user, require_admin
from memorytalk.backend.models.auth import PasswordChange
from memorytalk.backend.models.users import User, UserCreate, UserProfile, UserUpdate, UserView
from memorytalk.backend.services.auth import AuthError
from memorytalk.backend.services.users import UserService

router = APIRouter(prefix="/api/users", tags=["users"])


def users(request: Request) -> UserService:
    return request.app.state.users


@router.get("", response_model=Result[list[UserView]], summary="所有注册的 user,带活动统计,按最近活动倒序")
def list_users(svc: UserService = Depends(users)):
    return ok(svc.list())


@router.post("", response_model=Result[User], status_code=201, summary="建一个账号(admin;name 唯一;可带初始密码)")
def register(req: UserCreate, svc: UserService = Depends(users), _: str = Depends(require_admin)):
    return ok(svc.register(req))


@router.get("/me", response_model=Result[UserProfile], summary="我是谁:token 对应的档案")
def me(svc: UserService = Depends(users), who: str = Depends(current_user)):
    return ok(svc.profile(who))


@router.get("/{name}", response_model=Result[UserProfile], summary="一个 user 的档案 + 建的 / 动过的 work、最近的提交")
def get_user(name: str, svc: UserService = Depends(users)):
    return ok(svc.profile(name))


@router.put("/{name}", response_model=Result[User], summary="改档案(display_name / email):自己的,或 admin 改谁的都行")
def update_user(name: str, req: UserUpdate, request: Request, svc: UserService = Depends(users), who: str = Depends(current_user)):
    if name != who:
        require_admin(request)
    return ok(svc.update(name, req))


@router.put("/{name}/password", response_model=Result[dict], summary="改密码:自己的要带 old_password;admin 给别人设不用。改完这个人的 token 全部作废")
def set_password(name: str, req: PasswordChange, request: Request, who: str = Depends(current_user)):
    if name != who:
        require_admin(request)
        request.app.state.auth.set_password(name, req.new_password, check_old=False)
    else:
        if req.old_password is None:
            raise AuthError("unauthorized", "改自己的密码要带 old_password", 401)
        request.app.state.auth.set_password(name, req.new_password, req.old_password)
    return ok({})

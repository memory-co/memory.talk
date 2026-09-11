"""/api/users —— user 是注册的顶层对象:注册、档案、清单、我是谁。不做权限。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request

from memorytalk.backend.models.users import User, UserCreate, UserProfile, UserUpdate, UserView
from memorytalk.backend.services.users import UserService

router = APIRouter(prefix="/api/users", tags=["users"])


def users(request: Request) -> UserService:
    return request.app.state.users


@router.get("", response_model=list[UserView], summary="所有注册的 user,带活动统计,按最近活动倒序")
def list_users(svc: UserService = Depends(users)):
    return svc.list()


@router.post("", response_model=User, status_code=201, summary="注册一个 user(name 唯一;之后请求头 X-Memory-Talk-User 用它)")
def register(req: UserCreate, svc: UserService = Depends(users)):
    return svc.register(req)


@router.get("/me", response_model=UserProfile | None, summary="我是谁:X-Memory-Talk-User 对应的 user 档案(没带 → null)")
def me(svc: UserService = Depends(users), x_memory_talk_user: str | None = Header(None, alias="X-Memory-Talk-User")):
    return svc.profile(x_memory_talk_user) if x_memory_talk_user else None


@router.get("/{name}", response_model=UserProfile, summary="一个 user 的档案 + 建的 / 动过的 work、最近的提交")
def get_user(name: str, svc: UserService = Depends(users)):
    return svc.profile(name)


@router.put("/{name}", response_model=User, summary="改档案(display_name / email)")
def update_user(name: str, req: UserUpdate, svc: UserService = Depends(users)):
    return svc.update(name, req)

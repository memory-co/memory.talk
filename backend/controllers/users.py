"""/api/users —— user 是顶层对象:谁在这个实例里出现过、各自建了 / 动了哪些 work、提交了多少认知。不注册、不做权限。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request

from models.users import User, UserProfile
from services.users import UserService

router = APIRouter(prefix="/api/users", tags=["users"])


def users(request: Request) -> UserService:
    return request.app.state.users


@router.get("", response_model=list[User], summary="所有出现过的 user(从 work 与 collections 汇总),按最近活动倒序")
def list_users(svc: UserService = Depends(users)):
    return svc.list()


@router.get("/me", response_model=UserProfile | None, summary="我是谁:X-Memory-Talk-User 对应的 user(没带 → null)")
def me(svc: UserService = Depends(users), x_memory_talk_user: str | None = Header(None, alias="X-Memory-Talk-User")):
    if not x_memory_talk_user:
        return None
    try:
        return svc.get(x_memory_talk_user)
    except LookupError:
        return UserProfile(name=x_memory_talk_user)


@router.get("/{name}", response_model=UserProfile, summary="一个 user:建的 / 动过的 work、最近的提交")
def get_user(name: str, svc: UserService = Depends(users)):
    return svc.get(name)

"""user —— 团队里的一个人。**注册的实体**,和 work 平级,有自己的存储(docs/designs/v5/user.md)。
权限只有一档:admin 管账号(docs/designs/v5/auth.md),其余谁都能动。密码哈希存在记录里,任何模型都不带它出去。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class User(BaseModel):
    name: str = Field(description="唯一 id,也是请求头 X-Memory-Talk-User 里写的那个;commit author 的名字")
    display_name: str = ""
    email: str = Field("", description="commit author 的邮箱;空则用 <name>@memory.talk")
    created_at: str
    role: Literal["admin", "member"] = Field("member", description="admin 这个名字的账号固定是 admin;它管账号,别的没差别")


class UserCreate(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_.\-]{1,64}$")
    display_name: str = ""
    email: str = ""
    password: str = Field("", description="初始密码(admin 建账号时给);空 = 先不能登录,之后再设")


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None


class UserView(User):
    """档案 + 派生的活动统计(现算,不落盘)。"""
    works_created: int = 0
    works_touched: int = 0
    commits: int = Field(0, description="collections 里以它为 author 的提交数")
    active_works: list[str] = Field(default_factory=list, description="最近 ACTIVE_WINDOW 内动过的 work")
    last_seen: str = ""


class UserProfile(UserView):
    works_created_ids: list[str] = Field(default_factory=list)
    works_touched_ids: list[str] = Field(default_factory=list)
    recent_commits: list[dict] = Field(default_factory=list)

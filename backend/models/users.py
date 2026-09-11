"""user —— 团队里的一个人。不注册,出现过就存在;从 work 与 collections 里汇总(docs/designs/v5/user.md)。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class User(BaseModel):
    name: str
    works_created: int = 0
    works_touched: int = 0
    commits: int = Field(0, description="collections 里以它为 author 的提交数")
    active_works: list[str] = Field(default_factory=list, description="最近 ACTIVE_WINDOW 内动过的 work")
    last_seen: str = ""


class UserProfile(User):
    works_created_ids: list[str] = Field(default_factory=list)
    works_touched_ids: list[str] = Field(default_factory=list)
    recent_commits: list[dict] = Field(default_factory=list)

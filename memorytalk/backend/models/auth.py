"""auth —— 先立 admin,再进门(docs/designs/v5/auth.md)。token 是随机串,服务端只记它的哈希。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from memorytalk.backend.models.users import User


class AuthStatus(BaseModel):
    setup_required: bool = Field(description="还没有 admin 账号:除了 setup 什么都不能做")
    authenticated: bool = Field(description="这次请求带的 token 有效")
    user: User | None = Field(None, description="token 对应的账号")


class SetupRequest(BaseModel):
    password: str = Field(min_length=6, max_length=256)
    display_name: str = ""
    email: str = ""


class LoginRequest(BaseModel):
    name: str
    password: str


class LoginResult(BaseModel):
    token: str = Field(description="之后每个请求 Authorization: Bearer <token>")
    user: User


class PasswordChange(BaseModel):
    old_password: str | None = Field(None, description="改自己的要带;admin 给别人设不用")
    new_password: str = Field(min_length=6, max_length=256)

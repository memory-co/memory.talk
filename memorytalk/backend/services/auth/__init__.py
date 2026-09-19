"""auth:setup(立 admin)、登录(密码 → token)、解析 token、改密码。密码哈希用标准库 scrypt,不引依赖。docs/designs/v5/auth.md"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from memorytalk.backend.models.auth import LoginResult, SetupRequest
from memorytalk.backend.models.users import User, UserCreate
from memorytalk.backend.services.auth.repo import TokenRepo
from memorytalk.backend.services.users import UserService

ADMIN = "admin"


class AuthError(RuntimeError):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code, self.status = code, status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt, digest = stored.split("$", 2)
    calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=2 ** 14, r=8, p=1)
    return hmac.compare_digest(calc, base64.b64decode(digest))


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, users: UserService, tokens: TokenRepo) -> None:
        self.users = users
        self.tokens = tokens

    # ---- setup ----

    def setup_required(self) -> bool:
        return not self.users.exists(ADMIN)

    def setup(self, req: SetupRequest) -> LoginResult:
        if not self.setup_required():
            raise AuthError("not_found", "已经设过 admin 了", 404)
        user = self.users.register(UserCreate(name=ADMIN, display_name=req.display_name, email=req.email, password=req.password))
        return LoginResult(token=self.issue(user.name), user=user)

    # ---- token ----

    def login(self, name: str, password: str) -> LoginResult:
        record = self.users.repo.get(name)
        if record is None or not verify_password(password, record.get("password")):
            raise AuthError("unauthorized", "名字或密码不对", 401)
        return LoginResult(token=self.issue(name), user=User(**record))

    def issue(self, name: str) -> str:
        token = secrets.token_urlsafe(32)
        self.tokens.put(_digest(token), {"user": name, "created_at": _now()})
        return token

    def resolve(self, token: str | None) -> str | None:
        """token → 名字;不认识 / 账号没了 → None。"""
        if not token:
            return None
        data = self.tokens.get(_digest(token))
        if data is None or not self.users.exists(data["user"]):
            return None
        return data["user"]

    def logout(self, token: str | None) -> None:
        if token:
            self.tokens.delete(_digest(token))

    def revoke_all(self, name: str) -> None:
        for digest, data in self.tokens.list():
            if data.get("user") == name:
                self.tokens.delete(digest)

    # ---- 密码 ----

    def set_password(self, name: str, new_password: str, old_password: str | None = None, check_old: bool = True) -> None:
        """改密码;check_old 时要旧密码对得上。改完这个人的 token 全部作废。"""
        record = self.users.repo.get(name)
        if record is None:
            raise AuthError("not_found", f"user {name} 不存在", 404)
        if check_old and not verify_password(old_password or "", record.get("password")):
            raise AuthError("unauthorized", "旧密码不对", 401)
        record["password"] = hash_password(new_password)
        self.users.repo.put(name, record)
        self.revoke_all(name)


__all__ = ["AuthService", "AuthError", "ADMIN", "hash_password", "verify_password"]

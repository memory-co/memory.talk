"""auth:setup(立 admin)、登录(密码 → JWT)、解析 token、改密码。密码哈希用标准库 scrypt、JWT 用标准库 hmac,不引依赖。docs/designs/v5/auth.md

token 是 JWT(sub / iat / exp / jti):签名 + 过期不查存储就能验;jti 登记在 token 仓储里,logout / 换密码删掉它 = 立即作废。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

from memorytalk.backend.models.auth import LoginResult, SetupRequest
from memorytalk.backend.models.users import User, UserCreate
from memorytalk.backend.services.auth import jwt
from memorytalk.backend.services.auth.repo import TokenRepo
from memorytalk.backend.services.users import UserService

ADMIN = "admin"
TOKEN_TTL = 30 * 24 * 3600          # JWT 有效期:30 天;过了回登录页


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
    def __init__(self, users: UserService, tokens: TokenRepo, key: bytes) -> None:
        self.users = users
        self.tokens = tokens
        self.key = key

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
        now, jti = int(time.time()), secrets.token_urlsafe(16)
        self.tokens.put(_digest(jti), {"user": name, "created_at": _now(), "exp": now + TOKEN_TTL})
        return jwt.encode({"sub": name, "iat": now, "exp": now + TOKEN_TTL, "jti": jti}, self.key)

    def resolve(self, token: str | None) -> str | None:
        """token → 名字。先验签名和过期(伪造 / 过期的不碰存储),再看 jti 还登记着(没被 logout / 换密码作废)、账号还在。"""
        claims = jwt.decode(token, self.key) if token else None
        if claims is None:
            return None
        data = self.tokens.get(_digest(str(claims.get("jti"))))
        if data is None or data.get("user") != claims.get("sub") or not self.users.exists(data["user"]):
            return None
        return data["user"]

    def logout(self, token: str | None) -> None:
        claims = jwt.decode(token, self.key) if token else None
        if claims is not None:
            self.tokens.delete(_digest(str(claims.get("jti"))))

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


__all__ = ["AuthService", "AuthError", "ADMIN", "TOKEN_TTL", "hash_password", "verify_password"]

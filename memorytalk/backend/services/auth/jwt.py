"""JWT(HS256),标准库实现,不引依赖。只签 / 验这一种:header 固定 {"alg":"HS256","typ":"JWT"},别的 alg 一律不认(alg=none 之类的坑不存在)。
密钥是 <home>/jwt.key(首次启动生成,0600);换掉它 = 所有人重新登录。docs/designs/v5/auth.md §3"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

_HEADER = {"alg": "HS256", "typ": "JWT"}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode(claims: dict, key: bytes) -> str:
    head = _b64(json.dumps(_HEADER, separators=(",", ":")).encode()) + "." + _b64(json.dumps(claims, separators=(",", ":")).encode())
    return head + "." + _b64(hmac.new(key, head.encode(), hashlib.sha256).digest())


def decode(token: str, key: bytes, now: float | None = None) -> dict | None:
    """签名对、alg 是 HS256、没过期 → claims;否则 None(不说为什么:门外的人不需要知道)。"""
    try:
        head, body, sig = token.split(".")
        if json.loads(_unb64(head)) != _HEADER:
            return None
        if not hmac.compare_digest(_unb64(sig), hmac.new(key, (head + "." + body).encode(), hashlib.sha256).digest()):
            return None
        claims = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(claims, dict) or not isinstance(claims.get("exp"), (int, float)):
        return None
    return claims if claims["exp"] > (time.time() if now is None else now) else None


def load_key(home: Path) -> bytes:
    """<home>/jwt.key:有就读,没有就生成一把(32 字节随机,0600)。"""
    path = home / "jwt.key"
    if not path.exists():
        home.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(32))
    return path.read_bytes()

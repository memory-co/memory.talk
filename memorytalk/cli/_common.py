"""CLI 公共件:输出 / 错误 / 文本值 / --field 解析 / HTTP 客户端。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx

DEFAULT_SERVER = "http://127.0.0.1:8000"



class Fail(SystemExit):
    def __init__(self, message: str, code: int = 1) -> None:
        print(f"**error:** {message}", file=sys.stderr)
        super().__init__(code)


def out(data: Any, as_json: bool, text: str | None = None) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(text if text is not None else (data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2)))


def value(v: str) -> str:
    """文本 flag 的值:@<file> 逐字节读,@- 读 stdin,其余原样。"""
    if v == "@-":
        return sys.stdin.read()
    if v.startswith("@") and len(v) > 1:
        return Path(v[1:]).read_text(encoding="utf-8")
    return v


def parse_fields(items: list[str] | None) -> dict:
    """--field k=v(多次):值先按 JSON 解析(数字 / 列表 / 布尔),不行就当字符串;含逗号当列表;a.b=v 嵌套。"""
    data: dict = {}
    for item in items or []:
        if "=" not in item:
            raise Fail(f"--field 要写成 k=v:{item}", 2)
        k, v = item.split("=", 1)
        v = value(v)
        try:
            parsed: Any = json.loads(v)
        except json.JSONDecodeError:
            parsed = [_scalar(s.strip()) for s in v.split(",")] if "," in v and not v.startswith("@") else v
        cur = data
        parts = k.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = parsed
    return data


def _scalar(s: str) -> Any:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return s


# ================================================================ HTTP

class Api:
    def __init__(self, server: str, user: str | None, work: str | None, token: str | None = None) -> None:
        """token:--token / MEMORY_TALK_TOKEN,否则 credentials.json 里存的(--user 挑谁的,默认最近登录的)。"""
        from .auth import saved_token
        self.base = server.rstrip("/")
        self.user = user
        headers = {}
        if not token:
            self.user, token = saved_token(self.base, user)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if work:
            headers["X-Memory-Talk-Work"] = work
        self.c = httpx.Client(base_url=self.base, headers=headers, timeout=30)

    def call(self, method: str, path: str, *, params: dict | None = None, json_body: Any = None, text: bool = False) -> Any:
        try:
            r = self.c.request(method, path, params={k: v for k, v in (params or {}).items() if v is not None}, json=json_body)
        except httpx.ConnectError:
            raise Fail(f"连不上 {self.base};先 `memory.talk server start`", 3)
        try:
            body = r.json()
        except ValueError:
            body = None
        if r.status_code >= 400:
            msg = f"{body.get('error', r.status_code)}: {body.get('message')}" if isinstance(body, dict) else f"{r.status_code}: {r.text[:200]}"
            if isinstance(body, dict) and body.get("error") == "setup_required":
                msg += ";先 memory.talk setup"
            elif r.status_code == 401:
                msg += ";先 memory.talk login" + (f" --user {self.user}" if self.user else "")
            raise Fail(msg, 1)
        return body["data"] if isinstance(body, dict) and "data" in body else body   # 信封:{"data", "message"}



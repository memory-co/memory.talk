"""memory.talk setup / login / logout —— 门(docs/designs/v5/auth.md)。token 存在 <home>/credentials.json,按服务地址分开,一个地址可以存几个人的。"""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

from ._common import Fail, out


def credentials_path() -> Path:
    return Path(os.environ.get("MEMORY_TALK_HOME", "~/.memory.talk")).expanduser() / "credentials.json"


def load_credentials() -> dict:
    p = credentials_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def save_credentials(data: dict) -> None:
    p = credentials_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def saved_token(server: str, user: str | None) -> tuple[str | None, str | None]:
    """(名字, token):--user 指定就拿那个人的;不指定拿最近登录的。"""
    entry = load_credentials().get(server.rstrip("/")) or {}
    name = user or entry.get("current")
    return name, (entry.get("tokens") or {}).get(name) if name else None


def _remember(server: str, name: str, token: str) -> None:
    data = load_credentials()
    entry = data.setdefault(server.rstrip("/"), {"current": name, "tokens": {}})
    entry["current"] = name
    entry.setdefault("tokens", {})[name] = token
    save_credentials(data)


def _password(a, prompt: str) -> str:
    pw = a.password or os.environ.get("MEMORY_TALK_PASSWORD")
    if not pw:
        pw = getpass.getpass(prompt)
    if not pw:
        raise Fail("密码不能为空", 2)
    return pw


def a_setup(api, a):
    st = api.call("GET", "/api/auth/status")
    if not st["setup_required"]:
        raise Fail("已经设过 admin 了;要登录用 memory.talk login", 1)
    pw = _password(a, "给 admin 设一个密码: ")
    r = api.call("POST", "/api/auth/setup", json_body={"password": pw, "display_name": a.display_name or "", "email": a.email or ""})
    _remember(api.base, "admin", r["token"])
    out(r["user"], a.json, f"admin 建好了,已登录({credentials_path()})")


def a_login(api, a):
    name = a.name or a.user or "admin"
    pw = _password(a, f"{name} 的密码: ")
    r = api.call("POST", "/api/auth/login", json_body={"name": name, "password": pw})
    _remember(api.base, name, r["token"])
    out(r["user"], a.json, f"已登录 {name}({credentials_path()})")


def a_logout(api, a):
    name, token = saved_token(api.base, a.user)
    if not token:
        raise Fail("没登录", 1)
    try:
        api.call("POST", "/api/auth/logout")
    except Fail:
        pass                                   # token 早就作废了(比如密码被改),本地照样清掉
    data = load_credentials()
    entry = data.get(api.base, {})
    entry.get("tokens", {}).pop(name, None)
    if entry.get("current") == name:
        entry["current"] = next(iter(entry.get("tokens") or {}), None)
    save_credentials(data)
    out({}, a.json, f"已退出 {name}")


def register(top) -> None:
    p = top.add_parser("setup", help="首次:建 admin 账号并登录"); p.add_argument("--password"); p.add_argument("--display-name", dest="display_name"); p.add_argument("--email"); p.set_defaults(fn=a_setup)
    p = top.add_parser("login", help="登录(默认 admin;密码问你,或 --password / MEMORY_TALK_PASSWORD)"); p.add_argument("name", nargs="?", help="谁(默认 --user / MEMORY_TALK_USER,再默认 admin)"); p.add_argument("--password"); p.set_defaults(fn=a_login)
    top.add_parser("logout", help="退出登录(作废 token)").set_defaults(fn=a_logout)

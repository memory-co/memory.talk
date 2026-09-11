"""memory.talk 命令行:本地 API 的客户端,不含业务逻辑(docs/cli/v5)。

    memory.talk server   start | stop | restart | status | daemon
    memory.talk work     create | list | show | set | attach | sessions | detach | capture | rounds | inbox | manager | users | touch | recall | servers
    memory.talk user     add | list | show | set | whoami
    memory.talk collection (col)  layers | tree | ls | recall | search | read | write | edit | rm | log | act | manager | managed
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

DEFAULT_SERVER = "http://127.0.0.1:8000"


# ================================================================ 输出 / 错误

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
    def __init__(self, server: str, user: str | None, work: str | None) -> None:
        self.base = server.rstrip("/")
        headers = {}
        if user:
            headers["X-Memory-Talk-User"] = user
        if work:
            headers["X-Memory-Talk-Work"] = work
        self.c = httpx.Client(base_url=self.base, headers=headers, timeout=30)

    def call(self, method: str, path: str, *, params: dict | None = None, json_body: Any = None, text: bool = False) -> Any:
        try:
            r = self.c.request(method, path, params={k: v for k, v in (params or {}).items() if v is not None}, json=json_body)
        except httpx.ConnectError:
            raise Fail(f"连不上 {self.base};先 `memory.talk server start`", 3)
        if r.status_code >= 400:
            try:
                body = r.json()
                msg = f"{body.get('error', r.status_code)}: {body.get('message', body)}"
            except ValueError:
                msg = f"{r.status_code}: {r.text[:200]}"
            raise Fail(msg, 1)
        if r.status_code == 204:
            return None
        return r.text if text else r.json()


# ================================================================ server:后台守护

def _home() -> Path:
    return Path(os.environ.get("MEMORY_TALK_HOME", "~/.memory.talk")).expanduser()


def _instance_path() -> Path:
    return _home() / "instance.json"


def _read_instance() -> dict | None:
    try:
        return json.loads(_instance_path().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _health(url: str) -> bool:
    try:
        return httpx.get(f"{url}/api/system/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def server_start(a) -> None:
    inst = _read_instance()
    if inst and _alive(inst["pid"]) and _health(inst["url"]):
        print(f"memory.talk 已在跑(pid {inst['pid']}) {inst['url']}")
        return
    home = _home()
    home.mkdir(parents=True, exist_ok=True)
    log = open(home / "server.log", "ab")
    cmd = [sys.executable, "-m", "memorytalk", "server", "daemon", "--host", a.host, "--port", str(a.port)]
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            start_new_session=True, env={**os.environ, "MEMORY_TALK_HOME": str(home)})
    url = f"http://{a.host}:{a.port}"
    inst = {"pid": proc.pid, "url": url, "host": a.host, "port": a.port, "home": str(home),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "store": os.environ.get("MEMORY_TALK_STORE", "fs")}
    _instance_path().write_text(json.dumps(inst, indent=2))
    for _ in range(50):
        if _health(url):
            break
        if proc.poll() is not None:
            tail = (home / "server.log").read_text(errors="replace").splitlines()[-15:]
            raise Fail("起不来:\n" + "\n".join(tail), 1)
        time.sleep(0.2)
    else:
        raise Fail("10 秒内没就绪,看 " + str(home / "server.log"), 1)
    print(f"memory.talk 已启动(pid {proc.pid})\n  地址    {url}\n  文档    {url}/docs\n  存储    {inst['store']}  {home}\n"
          f"  日志    {home / 'server.log'}\n  停止    memory.talk server stop")


def server_stop(a) -> None:
    inst = _read_instance()
    if not inst or not _alive(inst["pid"]):
        print("memory.talk 没在跑")
        return
    os.kill(inst["pid"], signal.SIGTERM)
    for _ in range(25):
        if not _alive(inst["pid"]):
            break
        time.sleep(0.2)
    else:
        os.kill(inst["pid"], signal.SIGKILL)
    print(f"memory.talk 已停止(pid {inst['pid']})。tmux 会话不动,下次 start 后按登记重入")


def server_restart(a) -> None:
    inst = _read_instance() or {}
    server_stop(a)
    a.host = inst.get("host", a.host)
    a.port = inst.get("port", a.port)
    server_start(a)


def server_status(a) -> None:
    inst = _read_instance()
    ok = bool(inst and _alive(inst["pid"]) and _health(inst["url"]))
    if a.json:
        print(json.dumps({**(inst or {}), "running": ok}, indent=2))
    elif not ok:
        print("memory.talk 没在跑" + (f"(instance.json 里有 pid {inst['pid']},但进程或健康检查不通过)" if inst else ""))
    else:
        info = httpx.get(f"{inst['url']}/api/system/info", timeout=2).json()
        print(f"memory.talk 运行中(pid {inst['pid']})\n  地址     {inst['url']}\n  存储     {info['store']['backend']}  {info['home']}\n"
              f"  启动于   {inst['started_at']}\n  健康     ok\n  停止     memory.talk server stop")
    if not ok:
        raise SystemExit(1)


def server_daemon(a) -> None:
    import uvicorn
    uvicorn.run("memorytalk.backend.main:create_app", factory=True, host=a.host, port=a.port, log_level="info")


# ================================================================ work

def w_create(api, a): out(api.call("POST", "/api/works", json_body={"goal": value(a.goal), "parent": a.parent}), a.json, None)
def w_list(api, a):
    forest = api.call("GET", "/api/works", params={"root": a.root, "created_by": a.created_by})
    if a.json:
        return out(forest, True)
    def walk(nodes, depth):
        for n in nodes:
            if not a.all and n["status"] in ("done", "abandoned"):
                continue
            print(f"{'  ' * depth}{n['id']}  {n['status']:<9} {n.get('created_by') or '-':<8} {n['goal']}")
            walk(n["children"], depth + 1)
    walk(forest, 0)
def w_show(api, a):
    w = api.call("GET", f"/api/works/{a.work_id}")
    if a.json:
        return out({"work": w, "sessions": api.call("GET", f"/api/works/{a.work_id}/sessions"),
                    "users": api.call("GET", f"/api/works/{a.work_id}/users"),
                    "inbox": api.call("GET", f"/api/works/{a.work_id}/inbox")[-10:],
                    "manager": api.call("GET", f"/api/works/{a.work_id}/manager")}, True)
    print(f"{w['id']}  {w['status']}  建者 {w.get('created_by') or '-'}  父 {w.get('parent') or '-'}\n  {w['goal']}")
    for s in api.call("GET", f"/api/works/{a.work_id}/sessions"):
        print(f"  会话 {s['id']}  {s['uri']}  {'活着' if s['alive'] else '死了'}")
    u = api.call("GET", f"/api/works/{a.work_id}/users")
    print(f"  在动 {', '.join(x['user'] for x in u['current']) or '-'};动过 {', '.join(x['user'] for x in u['history']) or '-'}")
    print(f"  manager {api.call('GET', f'/api/works/{a.work_id}/manager')['work'] or '-'}")
    for i in api.call("GET", f"/api/works/{a.work_id}/inbox")[-5:]:
        print(f"  收件 {i['ts']}  [{i['layer']}] {i['path']}  {i['subject']}")
def w_set(api, a):
    body = {k: v for k, v in {"goal": value(a.goal) if a.goal else None, "status": a.status}.items() if v is not None}
    out(api.call("PATCH", f"/api/works/{a.work_id}", json_body=body), a.json)
def w_attach(api, a):
    s = api.call("POST", f"/api/works/{a.work_id}/sessions", json_body={"uri": a.uri})
    out(s, a.json, f"{s['id']}\n  窗    {s['window']['url'] or '无(只有把手)'}\n  把手  {s['handle']['kind']}: {', '.join(s['handle']['capabilities']) or '无'}\n  cwd   {s.get('cwd') or '-'}")
def w_sessions(api, a):
    ss = api.call("GET", f"/api/works/{a.work_id}/sessions")
    out(ss, a.json, "\n".join(f"{s['id']}  {s['uri']}  {'活着' if s['alive'] else '死了'}  {s['last_attached']}" for s in ss) or "(没有会话)")
def w_detach(api, a): api.call("DELETE", f"/api/works/{a.work_id}/sessions/{a.session_id}"); print("已回收")
def w_capture(api, a): print(api.call("GET", f"/api/works/{a.work_id}/sessions/{a.session_id}/capture", params={"lines": a.lines}, text=True), end="")
def w_rounds(api, a):
    rs = api.call("GET", f"/api/works/{a.work_id}/sessions/{a.session_id}/rounds")
    out(rs, a.json, "\n\n".join(f"[{i}] {r['role']}  {r.get('timestamp') or ''}\n{r['text']}" for i, r in enumerate(rs)))
def w_inbox(api, a):
    items = api.call("GET", f"/api/works/{a.work_id}/inbox")
    out(items, a.json, "\n".join(f"{i['ts']}  [{i['layer']}] {i['path']}  {i['subject']}  by {i.get('by') or '-'}  ← {i['routed_by'] or '/'}" for i in items) or "(空)")
def w_manager(api, a):
    if a.set:
        r = api.call("PUT", f"/api/works/{a.work_id}/manager", json_body={"work": a.set})
    elif a.unset:
        r = api.call("PUT", f"/api/works/{a.work_id}/manager", json_body={"work": None})
    else:
        r = api.call("GET", f"/api/works/{a.work_id}/manager")
    out(r, a.json, f"manager: {r['work'] or '-(根)'}")
def w_users(api, a):
    u = api.call("GET", f"/api/works/{a.work_id}/users")
    out(u, a.json, "\n".join(f"{x['user']:<10} {'在动' if x['active'] else '    '}  {x['ops']} 次  最近 {x['last_seen']}" for x in u["history"]) or "(还没人动过)")
def w_touch(api, a): out(api.call("POST", f"/api/works/{a.work_id}/users/touch"), a.json, "ok")
def w_recall(api, a): print(api.call("GET", f"/api/works/{a.work_id}/recall", params={"layer": a.layer, "dir": a.dir}, text=True))
def w_servers(api, a):
    ss = api.call("GET", "/api/works/servers")
    out(ss, a.json, "\n".join(f"{s['name']:<8} {', '.join(s['protocols']) or '(兜底)':<14} {s['description']}" for s in ss))


# ================================================================ user

def u_add(api, a): out(api.call("POST", "/api/users", json_body={"name": a.name, "display_name": a.display_name or "", "email": a.email or ""}), a.json)
def u_list(api, a):
    us = api.call("GET", "/api/users")
    out(us, a.json, "\n".join(f"{u['name']:<10} {u['display_name']:<10} 建 {u['works_created']} / 动 {u['works_touched']} 个 work  {u['commits']} 次提交"
                              f"  {'正在动 ' + ','.join(u['active_works']) if u['active_works'] else ''}  最近 {u['last_seen'] or '(还没动过)'}" for u in us))
def u_show(api, a):
    p = api.call("GET", f"/api/users/{a.name}")
    out(p, a.json, f"{p['name']}  {p['display_name']}  {p['email']}  注册于 {p['created_at']}\n  建的 work: {', '.join(p['works_created_ids']) or '-'}\n"
                   f"  动过的 work: {', '.join(p['works_touched_ids']) or '-'}\n" + "\n".join(f"  {c['date'][:19]}  {c['subject']}" for c in p["recent_commits"]))
def u_set(api, a):
    body = {k: v for k, v in {"display_name": a.display_name, "email": a.email}.items() if v is not None}
    out(api.call("PUT", f"/api/users/{a.name}", json_body=body), a.json)
def u_whoami(api, a):
    if not a.user:
        raise Fail("没设身份:--user <名字> 或 export MEMORY_TALK_USER=<名字>", 2)
    a.name = a.user
    u_show(api, a)


# ================================================================ collection

def c_layers(api, a):
    if a.add:
        out(api.call("POST", "/api/collections/layers", json_body={"name": a.add, "schema_yaml": Path(a.schema).read_text(), "reason": a.reason or ""}), a.json)
        return
    ls = api.call("GET", "/api/collections/layers")
    out(ls, a.json, "\n".join(f"{l['order']}  {l['name']:<10} {l['format']:<9} {('.' + l['name'] + '/') if l['suffix'] else '(不带后缀的一切)':<14} "
                              f"行为 {', '.join(l['behaviors']) or '-'}  {l['description']}" for l in ls))
def c_tree(api, a):
    items = api.call("GET", "/api/collections/tree", params={"path": a.path or ""})
    out(items, a.json, "\n".join(f"{i['name']:<40} {i['kind']:<7} {i.get('layer') or ''}" for i in items) or "(空)")
def c_ls(api, a): out(api.call("GET", f"/api/collections/{a.layer}", params={"dir": a.dir}), a.json, api.call("GET", f"/api/collections/{a.layer}/recall", params={"dir": a.dir}, text=True))
def c_recall(api, a): print(api.call("GET", f"/api/collections/{a.layer}/recall", params={"dir": a.dir}, text=True))
def c_search(api, a):
    hits = api.call("GET", "/api/collections/search", params={"q": a.query, "layer": a.layer})
    out(hits, a.json, "\n".join(f"[{h['layer']}] {h['path']}:{h['line']}  {h['text'].strip()}" for h in hits) or "(没找到)")
def c_read(api, a):
    o = api.call("GET", f"/api/collections/{a.layer}/{a.path}", params={"rev": a.rev})
    if a.json:
        return out(o, True)
    b = o["body"]
    if isinstance(b, str):
        print(b, end="" if b.endswith("\n") else "\n")
    elif a.layer == "issue":
        print(f"# {b['question']}\n出处 {b.get('origin') or '-'}  卡 {b.get('card') or '-'}")
        for p in b["positions"]:
            print(f"\n## {p['id']}  {p['claim']}   (+{p['up']} / -{p['down']} / 0:{p['neutral']}  credence {p['credence']})")
            for g in p["arguments"]:
                print(f"  {g['id']} {'+1' if g['stance'] == 1 else ('-1' if g['stance'] == -1 else ' 0')}  {g['comment']}  {g.get('evidence') or ''}")
        for l in b["links"]:
            print(f"边 {l['type']} → {l['target']}")
    else:
        meta = {k: v for k, v in b.items() if k != "body" and v not in (None, "", [])}
        print("---\n" + "\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n---\n\n" + (b.get("body") or ""))
def _payload(a) -> dict:
    if a.data:
        return json.loads(value(a.data))
    return parse_fields(a.field)
def c_write(api, a):
    body = {"content": value(a.content), "reason": a.reason or ""} if a.content else {"data": _payload(a), "reason": a.reason or ""}
    out(api.call("POST", f"/api/collections/{a.layer}/{a.path}", json_body=body), a.json, f"[{a.layer}] write {a.path}")
def c_edit(api, a):
    body = {"content": value(a.content), "reason": a.reason or ""} if a.content else {"data": _payload(a), "reason": a.reason or ""}
    out(api.call("PUT", f"/api/collections/{a.layer}/{a.path}", json_body=body), a.json, f"[{a.layer}] edit {a.path}")
def c_rm(api, a): api.call("DELETE", f"/api/collections/{a.layer}/{a.path}", params={"reason": a.reason}); print(f"[{a.layer}] delete {a.path}")
def c_log(api, a):
    revs = api.call("GET", f"/api/collections/history/{a.layer}/{a.path}")
    out(revs, a.json, "\n".join(f"{r['sha'][:7]}  {r['author']:<10} {r['date'][:19]}  {r['subject']}" + (f"\n         {r['body']}" if r['body'] else "") for r in revs))
def c_act(api, a):
    payload = parse_fields(a.field)
    if a.reason:
        payload["reason"] = a.reason
    out(api.call("POST", f"/api/collections/act/{a.layer}/{a.action}/{a.path}", json_body=payload), a.json, f"[{a.layer}] {a.action} {a.path}: ok")
def c_manager(api, a):
    if a.set:
        r = api.call("PUT", "/api/collections/manager", params={"path": a.path or ""}, json_body={"work": a.set, "reason": a.reason or ""})
    elif a.unset:
        api.call("DELETE", "/api/collections/manager", params={"path": a.path or "", "reason": a.reason or ""}); r = None
    else:
        r = api.call("GET", "/api/collections/manager", params={"path": a.path or ""})
    out(r, a.json, f"manager: {r['work']}  (在 {r['dir'] or '/'})" if r else "没人管")
def c_managed(api, a):
    items = api.call("GET", "/api/collections/managed", params={"work": a.work_filter})
    out(items, a.json, "\n".join(f"[{i['layer']}] {i['path']}  {i['name']}" for i in items) or "(无)")


# ================================================================ 装配

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="memory.talk", description="memory.talk v5 —— 跑 code agent 的工作台,记忆是它的副产物")
    ap.add_argument("--server", default=os.environ.get("MEMORY_TALK_SERVER", DEFAULT_SERVER), help="API 在哪")
    ap.add_argument("--user", default=os.environ.get("MEMORY_TALK_USER"), help="我是谁(须注册过)")
    ap.add_argument("--work", default=os.environ.get("MEMORY_TALK_WORK"), help="在哪个 work 里操作")
    ap.add_argument("--json", action="store_true", help="结构化输出")
    top = ap.add_subparsers(dest="cmd", required=True)

    # ---- server ----
    s = top.add_parser("server", help="本地 API 服务").add_subparsers(dest="sub", required=True)
    for name, fn in (("start", server_start), ("daemon", server_daemon), ("restart", server_restart)):
        p = s.add_parser(name); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8000); p.set_defaults(local=fn)
    s.add_parser("stop").set_defaults(local=server_stop)
    s.add_parser("status").set_defaults(local=server_status)

    # ---- work ----
    w = top.add_parser("work", help="work 树 / 会话 / 收件箱").add_subparsers(dest="sub", required=True)
    def wp(name, fn, *args, wid=True):
        p = w.add_parser(name)
        if wid:
            p.add_argument("work_id")
        for flags, kw in args:
            p.add_argument(*flags, **kw)
        p.set_defaults(fn=fn)
        return p
    wp("create", w_create, (["--goal"], {"required": True}), (["--parent"], {}), wid=False)
    wp("list", w_list, (["--root"], {}), (["--created-by"], {"dest": "created_by"}), (["--all"], {"action": "store_true"}), wid=False)
    wp("show", w_show)
    wp("set", w_set, (["--goal"], {}), (["--status"], {"choices": ["todo", "doing", "done", "abandoned"]}))
    wp("attach", w_attach, (["uri"], {}))
    wp("sessions", w_sessions)
    wp("detach", w_detach, (["session_id"], {}))
    wp("capture", w_capture, (["session_id"], {}), (["--lines"], {"type": int, "default": 200}))
    wp("rounds", w_rounds, (["session_id"], {}))
    wp("inbox", w_inbox)
    wp("manager", w_manager, (["--set"], {}), (["--unset"], {"action": "store_true"}))
    wp("users", w_users)
    wp("touch", w_touch)
    wp("recall", w_recall, (["--layer"], {"default": "card"}), (["--dir"], {"default": ""}))
    wp("servers", w_servers, wid=False)

    # ---- user ----
    u = top.add_parser("user", help="人:注册的实体").add_subparsers(dest="sub", required=True)
    p = u.add_parser("add"); p.add_argument("name"); p.add_argument("--display-name", dest="display_name"); p.add_argument("--email"); p.set_defaults(fn=u_add)
    u.add_parser("list").set_defaults(fn=u_list)
    p = u.add_parser("show"); p.add_argument("name"); p.set_defaults(fn=u_show)
    p = u.add_parser("set"); p.add_argument("name"); p.add_argument("--display-name", dest="display_name"); p.add_argument("--email"); p.set_defaults(fn=u_set)
    u.add_parser("whoami").set_defaults(fn=u_whoami)

    # ---- collection ----
    c = top.add_parser("collection", aliases=["col"], help="认知层").add_subparsers(dest="sub", required=True)
    p = c.add_parser("layers"); p.add_argument("add", nargs="?"); p.add_argument("--schema"); p.add_argument("--reason"); p.set_defaults(fn=c_layers)
    p = c.add_parser("tree"); p.add_argument("path", nargs="?"); p.set_defaults(fn=c_tree)
    p = c.add_parser("ls"); p.add_argument("layer"); p.add_argument("--dir", default=""); p.set_defaults(fn=c_ls)
    p = c.add_parser("recall"); p.add_argument("layer", nargs="?", default="card"); p.add_argument("--dir", default=""); p.set_defaults(fn=c_recall)
    p = c.add_parser("search"); p.add_argument("query"); p.add_argument("--layer"); p.set_defaults(fn=c_search)
    p = c.add_parser("read"); p.add_argument("layer"); p.add_argument("path"); p.add_argument("--rev"); p.set_defaults(fn=c_read)
    for name, fn in (("write", c_write), ("edit", c_edit)):
        p = c.add_parser(name); p.add_argument("layer"); p.add_argument("path")
        p.add_argument("--field", action="append"); p.add_argument("--data"); p.add_argument("--content"); p.add_argument("--reason"); p.set_defaults(fn=fn)
    p = c.add_parser("rm"); p.add_argument("layer"); p.add_argument("path"); p.add_argument("--reason", default=""); p.set_defaults(fn=c_rm)
    p = c.add_parser("log"); p.add_argument("layer"); p.add_argument("path"); p.set_defaults(fn=c_log)
    p = c.add_parser("act"); p.add_argument("layer"); p.add_argument("action"); p.add_argument("path"); p.add_argument("--field", action="append"); p.add_argument("--reason"); p.set_defaults(fn=c_act)
    p = c.add_parser("manager"); p.add_argument("path", nargs="?"); p.add_argument("--set"); p.add_argument("--unset", action="store_true"); p.add_argument("--reason"); p.set_defaults(fn=c_manager)
    p = c.add_parser("managed"); p.add_argument("--work", dest="work_filter"); p.set_defaults(fn=c_managed)
    return ap


def main(argv: list[str] | None = None) -> None:
    a = build_parser().parse_args(argv)
    if getattr(a, "local", None):
        a.local(a)
        return
    a.fn(Api(a.server, a.user, a.work), a)


if __name__ == "__main__":
    main()

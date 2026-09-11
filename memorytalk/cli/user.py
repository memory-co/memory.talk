"""memory.talk user —— 注册的实体:add / list / show / set / whoami。"""
from __future__ import annotations

from ._common import Fail, out



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




def register(top) -> None:
    u = top.add_parser("user", help="人:注册的实体").add_subparsers(dest="sub", required=True)
    p = u.add_parser("add"); p.add_argument("name"); p.add_argument("--display-name", dest="display_name"); p.add_argument("--email"); p.set_defaults(fn=u_add)
    u.add_parser("list").set_defaults(fn=u_list)
    p = u.add_parser("show"); p.add_argument("name"); p.set_defaults(fn=u_show)
    p = u.add_parser("set"); p.add_argument("name"); p.add_argument("--display-name", dest="display_name"); p.add_argument("--email"); p.set_defaults(fn=u_set)
    u.add_parser("whoami").set_defaults(fn=u_whoami)

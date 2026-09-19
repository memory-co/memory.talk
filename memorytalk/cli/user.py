"""memory.talk user —— 注册的实体:add(admin)/ list / show / set / whoami / passwd。"""
from __future__ import annotations

from ._common import Fail, out



def u_add(api, a): out(api.call("POST", "/api/users", json_body={"name": a.name, "display_name": a.display_name or "", "email": a.email or "", "password": a.password or ""}), a.json)
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
    p = api.call("GET", "/api/users/me")
    out(p, a.json, f"{p['name']}  {p['display_name']}  {p['email']}  {p['role']}  注册于 {p['created_at']}\n  建的 work: {', '.join(p['works_created_ids']) or '-'}\n"
                   f"  动过的 work: {', '.join(p['works_touched_ids']) or '-'}\n" + "\n".join(f"  {c['date'][:19]}  {c['subject']}" for c in p["recent_commits"]))
def u_passwd(api, a):
    body = {"new_password": a.new_password or _ask("新密码: ")}
    if not a.name or a.name == api.user:
        body["old_password"] = a.old_password or _ask("旧密码: ")
    api.call("PUT", f"/api/users/{a.name or api.user}/password", json_body=body)
    out({}, a.json, "密码已改;这个人的登录态全部作废,重新 login")
def _ask(prompt):
    import getpass
    v = getpass.getpass(prompt)
    if not v:
        raise Fail("密码不能为空", 2)
    return v




def register(top) -> None:
    u = top.add_parser("user", help="人:注册的实体").add_subparsers(dest="sub", required=True)
    p = u.add_parser("add"); p.add_argument("name"); p.add_argument("--display-name", dest="display_name"); p.add_argument("--email"); p.add_argument("--password"); p.set_defaults(fn=u_add)
    u.add_parser("list").set_defaults(fn=u_list)
    p = u.add_parser("show"); p.add_argument("name"); p.set_defaults(fn=u_show)
    p = u.add_parser("set"); p.add_argument("name"); p.add_argument("--display-name", dest="display_name"); p.add_argument("--email"); p.set_defaults(fn=u_set)
    u.add_parser("whoami").set_defaults(fn=u_whoami)
    p = u.add_parser("passwd", help="改密码:自己的(要旧密码)或 admin 给 <name> 设"); p.add_argument("name", nargs="?"); p.add_argument("--old-password", dest="old_password"); p.add_argument("--new-password", dest="new_password"); p.set_defaults(fn=u_passwd)

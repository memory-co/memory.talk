"""memory.talk work —— work 树、工作单元、收件箱、manager、users、召回、work server 清单。"""
from __future__ import annotations

from ._common import out, value



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
        return out({"work": w, "worklets": api.call("GET", f"/api/works/{a.work_id}/worklets"),
                    "users": api.call("GET", f"/api/works/{a.work_id}/users"),
                    "inbox": api.call("GET", f"/api/works/{a.work_id}/inbox")[-10:],
                    "manager": api.call("GET", f"/api/works/{a.work_id}/manager")}, True)
    print(f"{w['id']}  {w['status']}  建者 {w.get('created_by') or '-'}  父 {w.get('parent') or '-'}\n  {w['goal']}")
    for s in api.call("GET", f"/api/works/{a.work_id}/worklets"):
        print(f"  工作单元 {s['id']}  {s['uri']}  {'活着' if s['alive'] else '死了'}")
    u = api.call("GET", f"/api/works/{a.work_id}/users")
    print(f"  在动 {', '.join(x['user'] for x in u['current']) or '-'};动过 {', '.join(x['user'] for x in u['history']) or '-'}")
    print(f"  manager {api.call('GET', f'/api/works/{a.work_id}/manager')['work'] or '-'}")
    for i in api.call("GET", f"/api/works/{a.work_id}/inbox")[-5:]:
        print(f"  收件 {i['ts']}  [{i['layer']}] {i['path']}  {i['subject']}")
def w_set(api, a):
    body = {k: v for k, v in {"goal": value(a.goal) if a.goal else None, "status": a.status}.items() if v is not None}
    out(api.call("PATCH", f"/api/works/{a.work_id}", json_body=body), a.json)
def w_attach(api, a):
    s = api.call("POST", f"/api/works/{a.work_id}/worklets", json_body={"uri": a.uri})
    out(s, a.json, f"{s['id']}\n  窗    {s['window']['url'] or '无(只有把手)'}\n  把手  {s['handle']['kind']}: {', '.join(s['handle']['capabilities']) or '无'}\n  cwd   {s.get('cwd') or '-'}")
def w_worklets(api, a):
    ss = api.call("GET", f"/api/works/{a.work_id}/worklets")
    out(ss, a.json, "\n".join(f"{s['id']}  {s['uri']}  {'活着' if s['alive'] else '死了'}  {s['last_attached']}" for s in ss) or "(没有工作单元)")
def w_detach(api, a): api.call("DELETE", f"/api/works/{a.work_id}/worklets/{a.worklet_id}"); print("已回收")
def w_capture(api, a): print(api.call("GET", f"/api/works/{a.work_id}/worklets/{a.worklet_id}/capture", params={"lines": a.lines}, text=True), end="")
def w_rounds(api, a):
    rs = api.call("GET", f"/api/works/{a.work_id}/worklets/{a.worklet_id}/rounds")
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
def w_servers(api, a):
    ss = api.call("GET", "/api/works/servers")
    out(ss, a.json, "\n".join(f"{s['name']:<8} {', '.join(s['protocols']) or '(兜底)':<14} {s['description']}" for s in ss))




def register(top) -> None:
    w = top.add_parser("work", help="work 树 / 工作单元 / 收件箱").add_subparsers(dest="sub", required=True)

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
    wp("worklets", w_worklets)
    wp("detach", w_detach, (["worklet_id"], {}))
    wp("capture", w_capture, (["worklet_id"], {}), (["--lines"], {"type": int, "default": 200}))
    wp("rounds", w_rounds, (["worklet_id"], {}))
    wp("inbox", w_inbox)
    wp("manager", w_manager, (["--set"], {}), (["--unset"], {"action": "store_true"}))
    wp("users", w_users)
    wp("touch", w_touch)
    wp("servers", w_servers, wid=False)

"""memory.talk collection(col)—— 认知层:层、树、检索、对象 CRUD、历史、行为、manager。"""
from __future__ import annotations

import json
from pathlib import Path

from ._common import out, parse_fields, value



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




def register(top) -> None:
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

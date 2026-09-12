"""memory.talk collection(col)—— 认知层:层、树、检索、对象(目录里的文件)CRUD、历史。"""
from __future__ import annotations

import json
from pathlib import Path

from ._common import out, value



def c_layers(api, a):
    if a.add:
        out(api.call("POST", "/api/collections/layers", json_body={"name": a.add, "schema_yaml": Path(a.schema).read_text(), "reason": a.reason or ""}), a.json)
        return
    ls = api.call("GET", "/api/collections/layers")
    out(ls, a.json, "\n".join(f"{l['order']}  {l['name']:<10} {('.' + l['name'] + '/') if l['suffix'] else '-':<12} "
                              f"{', '.join(l['files']) or '(不带后缀的一切)':<40} {l['description']}" for l in ls))
def c_tree(api, a):
    items = api.call("GET", "/api/collections/tree", params={"path": a.path or ""})
    out(items, a.json, "\n".join(f"{i['name']:<40} {i['kind']:<7} {i.get('layer') or ''}" for i in items) or "(空)")
def _catalog(d, indent=0):
    lines = [f"{'  ' * indent}- {o['title']}  ({o['path']})" for o in d["objects"]]
    for sub in d["subdirs"]:
        lines.append(f"{'  ' * indent}{sub['dir'].rsplit('/', 1)[-1]}/")
        lines.extend(_catalog(sub, indent + 1))
    return lines
def c_ls(api, a):
    cat = api.call("GET", f"/api/collections/{a.layer}", params={"dir": a.dir})
    out(cat, a.json, "\n".join(_catalog(cat)) or "(空)")
def c_search(api, a):
    hits = api.call("GET", "/api/collections/search", params={"q": a.query, "layer": a.layer})
    out(hits, a.json, "\n".join(f"[{h['layer']}] {h['path']}:{h['line']}  {h['text'].strip()}" for h in hits) or "(没找到)")
def c_read(api, a):
    o = api.call("GET", f"/api/collections/{a.layer}/{a.path}", params={"rev": a.rev})
    if a.json:
        return out(o, True)
    if o.get("content") is not None:
        print(o["content"], end="" if o["content"].endswith("\n") else "\n")
        return
    print(f"# {o['title']}")
    for rel, text in o["files"].items():
        print(f"\n== {rel}\n{text.rstrip(chr(10))}")
def _body(a) -> dict:
    body = {"reason": a.reason or "", "subject": a.subject}
    if a.content:
        body["content"] = value(a.content)
    if a.put:
        files = {}
        for item in a.put:
            if "=" not in item:
                raise SystemExit(f"--put 要写成 <文件>=<内容|@file|@-|null>:{item}")
            rel, v = item.split("=", 1)
            files[rel] = None if v == "null" else value(v)
        body["files"] = files
    return body
def c_write(api, a): out(api.call("POST", f"/api/collections/{a.layer}/{a.path}", json_body=_body(a)), a.json, f"[{a.layer}] {a.subject or 'write ' + a.path}")
def c_edit(api, a): out(api.call("PUT", f"/api/collections/{a.layer}/{a.path}", json_body=_body(a)), a.json, f"[{a.layer}] {a.subject or 'edit ' + a.path}")
def c_rm(api, a): api.call("DELETE", f"/api/collections/{a.layer}/{a.path}", params={"reason": a.reason}); print(f"[{a.layer}] delete {a.path}")
def c_log(api, a):
    revs = api.call("GET", f"/api/collections/history/{a.layer}/{a.path}")
    out(revs, a.json, "\n".join(f"{r['sha'][:7]}  {r['author']:<10} {r['date'][:19]}  {r['subject']}" + (f"\n         {r['body']}" if r['body'] else "") for r in revs))
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
    p = c.add_parser("search"); p.add_argument("query"); p.add_argument("--layer"); p.set_defaults(fn=c_search)
    p = c.add_parser("read"); p.add_argument("layer"); p.add_argument("path"); p.add_argument("--rev"); p.set_defaults(fn=c_read)
    for name, fn in (("write", c_write), ("edit", c_edit)):
        p = c.add_parser(name); p.add_argument("layer"); p.add_argument("path")
        p.add_argument("--put", action="append", metavar="FILE=CONTENT", help="目录里的文件;内容可 @file / @-;edit 时 null 删")
        p.add_argument("--content", help="origin:原文(可 @file / @-)"); p.add_argument("--subject", help="提交信息的主题"); p.add_argument("--reason"); p.set_defaults(fn=fn)
    p = c.add_parser("rm"); p.add_argument("layer"); p.add_argument("path"); p.add_argument("--reason", default=""); p.set_defaults(fn=c_rm)
    p = c.add_parser("log"); p.add_argument("layer"); p.add_argument("path"); p.set_defaults(fn=c_log)
    # manager / managed 暂时注释掉,等 work 实现后一起启用(后端路由也注释了)
    # p = c.add_parser("manager"); p.add_argument("path", nargs="?"); p.add_argument("--set"); p.add_argument("--unset", action="store_true"); p.add_argument("--reason"); p.set_defaults(fn=c_manager)
    # p = c.add_parser("managed"); p.add_argument("--work", dest="work_filter"); p.set_defaults(fn=c_managed)

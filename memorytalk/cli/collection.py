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
    lines = []
    for l in ls:
        files = ", ".join(f"{f['pattern']}({f['format']}{'*' if f['required'] else ''})" for f in l["files"]) or "(不带后缀的一切)"
        lines.append(f"{l['order']}  {l['name']:<10} {('.' + l['name'] + '/') if l['suffix'] else '-':<12} {files}  行为 {', '.join(l['behaviors']) or '-'}  {l['description']}")
    out(ls, a.json, "\n".join(lines))
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
    b = o["body"]
    if isinstance(b, str):
        print(b, end="" if b.endswith("\n") else "\n")
    elif a.layer == "issue":
        print(f"# {o['title']}")
        if b["readme"].strip():
            print("\n" + b["readme"].rstrip("\n"))
        if b["summary"]:
            print(f"\n总结:{b['summary']}")
        for i, p in enumerate(b["positions"], 1):
            print(f"\n## {i}. {p['claim']}" + (f"   ← {p['note']}" if p["note"] else ""))
            if p["body"].strip():
                print(p["body"].rstrip("\n"))
            for g in p["arguments"]:
                print(f"  - {g}")
        for l in b["links"]:
            print(f"边 {l['type']} → {l['target']}")
    elif isinstance(b, dict) and set(o["files"]) == {o["files"][0]} and "body" in b:
        meta = {k: v for k, v in b.items() if k != "body" and v not in (None, "", [])}
        print("---\n" + "\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n---\n\n" + (b.get("body") or ""))
    else:
        for rel in o["files"]:
            print(f"== {rel}")
            v = b.get(rel) if isinstance(b, dict) else None
            print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=2))
def _payload(a) -> dict:
    if a.data:
        return json.loads(value(a.data))
    return parse_fields(a.field)
def _body(a) -> dict:
    body = {"reason": a.reason or ""}
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
    if a.field or a.data:
        body["data"] = _payload(a)
    return body
def c_write(api, a): out(api.call("POST", f"/api/collections/{a.layer}/{a.path}", json_body=_body(a)), a.json, f"[{a.layer}] write {a.path}")
def c_edit(api, a): out(api.call("PUT", f"/api/collections/{a.layer}/{a.path}", json_body=_body(a)), a.json, f"[{a.layer}] edit {a.path}")
def c_rm(api, a): api.call("DELETE", f"/api/collections/{a.layer}/{a.path}", params={"reason": a.reason}); print(f"[{a.layer}] delete {a.path}")
def c_log(api, a):
    revs = api.call("GET", f"/api/collections/history/{a.layer}/{a.path}")
    out(revs, a.json, "\n".join(f"{r['sha'][:7]}  {r['author']:<10} {r['date'][:19]}  {r['subject']}" + (f"\n         {r['body']}" if r['body'] else "") for r in revs))
def c_act(api, a):
    payload = json.loads(value(a.data)) if a.data else parse_fields(a.field)
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
    p = c.add_parser("search"); p.add_argument("query"); p.add_argument("--layer"); p.set_defaults(fn=c_search)
    p = c.add_parser("read"); p.add_argument("layer"); p.add_argument("path"); p.add_argument("--rev"); p.set_defaults(fn=c_read)
    for name, fn in (("write", c_write), ("edit", c_edit)):
        p = c.add_parser(name); p.add_argument("layer"); p.add_argument("path")
        p.add_argument("--put", action="append", metavar="FILE=CONTENT", help="目录里的文件;内容可 @file / @-;null 删")
        p.add_argument("--field", action="append"); p.add_argument("--data"); p.add_argument("--content"); p.add_argument("--reason"); p.set_defaults(fn=fn)
    p = c.add_parser("rm"); p.add_argument("layer"); p.add_argument("path"); p.add_argument("--reason", default=""); p.set_defaults(fn=c_rm)
    p = c.add_parser("log"); p.add_argument("layer"); p.add_argument("path"); p.set_defaults(fn=c_log)
    p = c.add_parser("act"); p.add_argument("layer"); p.add_argument("action"); p.add_argument("path"); p.add_argument("--field", action="append"); p.add_argument("--data", help="整个 payload 的 JSON(可 @file / @-)"); p.add_argument("--reason"); p.set_defaults(fn=c_act)
    # manager / managed 暂时注释掉,等 work 实现后一起启用(后端路由也注释了)
    # p = c.add_parser("manager"); p.add_argument("path", nargs="?"); p.add_argument("--set"); p.add_argument("--unset", action="store_true"); p.add_argument("--reason"); p.set_defaults(fn=c_manager)
    # p = c.add_parser("managed"); p.add_argument("--work", dest="work_filter"); p.set_defaults(fn=c_managed)

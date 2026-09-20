"""memory.talk search —— 综合搜索。"""
from __future__ import annotations

from ._common import out


def c_search(api, a):
    r = api.call("GET", "/api/search", params={"q": a.query, "limit": a.limit})
    lines = []
    for h in r["hits"]:
        if h["kind"] == "work":
            lines.append(f"[work] {h['id']}  {h['title']}  ({h['status']})")
        elif h["kind"] == "meta":
            lines.append(f"[{h['layer']}] {h['id']}:{h['line']}  {h['snippet'].strip()}")
        else:
            lines.append(f"[user] {h['id']}  {h['title']}" + (f"  {h['snippet']}" if h['snippet'] else ""))
    out(r, a.json, "\n".join(lines) or "(没找到)")


def register(top) -> None:
    p = top.add_parser("search", help="综合搜索:工作 / 元认知 / 成员")
    p.add_argument("query"); p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=c_search)

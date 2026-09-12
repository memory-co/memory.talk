"""issue —— 议事层(docs/designs/v5/issue.md)。对象 = `<path>.issue/` 目录:

    readme.md            问题的展开;纯 markdown;标题就是目录名
    meta.yaml            links[](和别的 issue 的边)+ positions[](manager 的排序)+ summary
    positions/<主张>.md  一个立场一个文件:阐述 + `## 论证` 下一行一条

这个模块就是这个目录的校验器;下面的行为只是校验器之上的快捷方式(和直接提交文件走同一个门)。
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ._spec import FileRule, LayerSpec, fields_of

LinkType = Literal["specializes", "suggested_by", "questions", "replaces", "related"]
ARGS_HEADING = "## 论证"
_ARG = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")


# ---- meta.yaml ----

class Link(BaseModel):
    type: LinkType
    target: str = Field(min_length=1, description="对端 issue 的 path;suggested_by 可带 #<主张>")


class Ranked(BaseModel):
    claim: str = Field(min_length=1, description="= positions/ 下的文件名")
    note: str = ""


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    links: list[Link] = Field(default_factory=list)
    positions: list[Ranked] = Field(default_factory=list, description="manager 的判定:排前面的当前占优")
    summary: str = ""


def check_meta(rel: str, meta: dict, parsed: dict[str, Any]) -> None:
    seen = set()
    for l in meta["links"]:
        key = (l["type"], l["target"])
        if key in seen:
            raise ValueError(f"links 里重复:{l['type']} {l['target']}")
        seen.add(key)
    claims = {position_claim(p) for p in parsed if p.startswith("positions/")}
    for r in meta["positions"]:
        if r["claim"] not in claims:
            raise ValueError(f"positions 里的 {r['claim']!r} 不是 positions/ 下已有的立场")


def check_position(rel: str, text: str, parsed: dict[str, Any]) -> None:
    claim = position_claim(rel)
    if not claim or "/" in claim or claim in (".", ".."):
        raise ValueError("主张(文件名)不能为空、不能含 /")


def position_claim(rel: str) -> str:
    return rel[len("positions/"):-len(".md")]


# ---- 读视图:三样合起来 ----

def arguments_of(text: str) -> list[str]:
    """`## 论证` 之后的列表行,一行一条。"""
    out, on = [], False
    for line in text.splitlines():
        if line.strip() == ARGS_HEADING:
            on = True
            continue
        if on and line.startswith("#"):
            on = False
        if on and (m := _ARG.match(line)):
            out.append(m.group(1))
    return out


def view(parsed: dict[str, Any], path: str) -> dict:
    meta = parsed.get("meta.yaml") or Meta().model_dump()
    files = {position_claim(rel): text for rel, text in parsed.items() if rel.startswith("positions/") and rel.endswith(".md")}
    order = [r["claim"] for r in meta["positions"]] + sorted(c for c in files if c not in {r["claim"] for r in meta["positions"]})
    notes = {r["claim"]: r["note"] for r in meta["positions"]}
    positions = [{"claim": c, "note": notes.get(c, ""), "body": files[c], "arguments": arguments_of(files[c])}
                 for c in order if c in files]
    return {"readme": parsed.get("readme.md", ""), "positions": positions, "links": meta["links"], "summary": meta["summary"]}


# ---- 行为:预制好的文件改动 + 一条像样的提交信息。签名统一 (collections, path, payload, ctx) -> view ----

def _meta(collections, path: str) -> dict:
    raw = collections.file("issue", path, "meta.yaml")
    return META_FILE.parse(raw) if raw else Meta().model_dump()


def position(collections, path: str, payload: dict, ctx) -> dict:
    """加一个立场:新建 positions/<claim>.md。payload: claim, body?, reason?"""
    from memorytalk.backend.services.collections import CollectionsError
    claim = str(payload["claim"]).strip()
    rel = f"positions/{claim}.md"
    if collections.file("issue", path, rel) is not None:
        raise CollectionsError("exists", f"立场已存在:{claim}", 409)
    collections.put("issue", path, {rel: (payload.get("body") or "").encode()}, payload.get("reason", ""), ctx,
                    subject=f"position {path}: {claim}")
    return collections.get("issue", path).body


def argue(collections, path: str, payload: dict, ctx) -> dict:
    """给某个立场追加一条论证:`## 论证` 下加一行。payload: claim, comment, reason?"""
    from memorytalk.backend.services.collections import CollectionsError
    claim, comment = str(payload["claim"]), str(payload["comment"]).strip()
    rel = f"positions/{claim}.md"
    raw = collections.file("issue", path, rel)
    if raw is None:
        raise CollectionsError("not_found", f"{claim} 不是这个 issue 的立场", 404)
    text = raw.decode("utf-8", "replace").rstrip("\n")
    if ARGS_HEADING not in text.splitlines():
        text = (text + "\n\n" if text else "") + ARGS_HEADING + "\n"
    text = text.rstrip("\n") + f"\n- {comment}\n"
    collections.put("issue", path, {rel: text.encode()}, payload.get("reason", ""), ctx,
                    subject=f"argue {path}#{claim}: {comment[:60]}")
    return collections.get("issue", path).body


def link(collections, path: str, payload: dict, ctx) -> dict:
    """连一条边:meta.yaml 的 links 追加。payload: type, target, reason?"""
    meta = _meta(collections, path)
    edge = Link(type=payload["type"], target=payload["target"]).model_dump()
    if edge not in meta["links"]:
        meta["links"].append(edge)
        collections.put("issue", path, {"meta.yaml": META_FILE.serialize(meta)}, payload.get("reason", ""), ctx,
                        subject=f"link {path} {edge['type']} {edge['target']}")
    return collections.get("issue", path).body


def rank(collections, path: str, payload: dict, ctx) -> dict:
    """manager 的判定:整体替换 meta.yaml 的 positions 和 summary。payload: positions[]{claim, note?}, summary?, reason?"""
    meta = _meta(collections, path)
    meta["positions"] = [Ranked.model_validate(p).model_dump() for p in payload.get("positions", [])]
    if "summary" in payload:
        meta["summary"] = payload["summary"] or ""
    first = meta["positions"][0]["claim"] if meta["positions"] else "-"
    collections.put("issue", path, {"meta.yaml": META_FILE.serialize(meta)}, payload.get("reason", ""), ctx,
                    subject=f"rank {path}: {first}")
    return collections.get("issue", path).body


README_FILE = FileRule("readme.md", "markdown", required=True, description="问题的展开;可空")
META_FILE = FileRule("meta.yaml", "yaml", model=Meta, check=check_meta, description="links / positions(排序)/ summary")
META_FILE.fields = fields_of(Meta)
POSITION_FILE = FileRule("positions/*.md", "markdown", check=check_position, description="一个立场;文件名 = 主张;## 论证 下一行一条")

LAYER = LayerSpec(
    name="issue", files=[README_FILE, META_FILE, POSITION_FILE], title="dirname", builtin=True,
    behaviors={"position": position, "argue": argue, "link": link, "rank": rank},
    view=view,
    description="议事:一个问题(目录名)+ 立场(positions/ 一个一文件)+ 论证(立场文件里一行一条)+ 边和排序(meta.yaml)。立场 / 论证只增不改;排序是 manager 的判定。",
)

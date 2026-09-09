"""issue —— 议事层:问题 + 立场 + 论证 + IBIS 边(docs/designs/v5/issue.md)。
对象 = `<path>.issue/issue.json`;manager 在同目录的 manager.json;id 就是 path。"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from models.collect import FieldSpec
from ._spec import LayerSpec, fields_of

Stance = Literal[1, 0, -1]
LinkType = Literal["specializes", "suggested_by", "questions", "replaces", "related"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Origin(BaseModel):
    """出处:work 的哪些 round,或 Collect 里的一个 origin 路径。"""
    work_id: str | None = None
    rounds: list[int] = Field(default_factory=list)
    origin: str | None = Field(None, description="origin 层里的一个路径(原文)")


class Argument(BaseModel):
    id: str
    stance: Stance
    comment: str = ""
    evidence: Origin | None = None
    work_id: str | None = None
    created_at: str


class Position(BaseModel):
    id: str
    claim: str
    origin: Origin | None = None
    arguments: list[Argument] = Field(default_factory=list)
    spawned_works: list[str] = Field(default_factory=list)
    created_at: str


class IssueLink(BaseModel):
    type: LinkType
    target: str = Field(description="对端 issue 的 path;suggested_by 也可写 <path>#<position_id>")


class Issue(BaseModel):
    question: str
    origin: Origin | None = None
    card: str | None = Field(None, description="争完写成的卡 / 挂在哪张卡上当讨论页(card 的 path)")
    positions: list[Position] = Field(default_factory=list)
    links: list[IssueLink] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)


# ---- 读视图:现算 ----

def view(issue: dict) -> dict:
    out = dict(issue)
    positions = []
    for p in issue.get("positions", []):
        up = sum(1 for a in p["arguments"] if a["stance"] == 1)
        down = sum(1 for a in p["arguments"] if a["stance"] == -1)
        neutral = sum(1 for a in p["arguments"] if a["stance"] == 0)
        positions.append({**p, "up": up, "down": down, "neutral": neutral, "credence": up - down})
    positions.sort(key=lambda p: p["credence"], reverse=True)
    out["positions"] = positions
    return out


# ---- 行为:schema 之上的领域动作。签名统一 (collect, path, payload, ctx) -> Obj ----

def _position(issue: dict, pid: str) -> dict:
    for p in issue["positions"]:
        if p["id"] == pid:
            return p
    from services.collect import CollectError
    raise CollectError("not_found", f"{pid} 不是这个 issue 的立场", 404)


def position(collect, path: str, payload: dict, ctx) -> dict:
    """加一个立场(只增不改)。payload: claim, origin?, reason?"""
    issue = collect.get("issue", path).body
    pos = Position(id=f"p{len(issue['positions']) + 1}", claim=payload["claim"],
                   origin=payload.get("origin"), created_at=now()).model_dump()
    issue["positions"].append(pos)
    collect.write("issue", path, issue, f"position {path}#{pos['id']}: {pos['claim'][:60]}",
                  payload.get("reason", ""), ctx)
    return view(issue)


def argue(collect, path: str, payload: dict, ctx) -> dict:
    """对某个立场表态。payload: position, stance, comment?, evidence?, work_id?, reason?"""
    issue = collect.get("issue", path).body
    pos = _position(issue, payload["position"])
    arg = Argument(id=f"a{len(pos['arguments']) + 1}", stance=payload["stance"], comment=payload.get("comment", ""),
                   evidence=payload.get("evidence"), work_id=payload.get("work_id"), created_at=now()).model_dump()
    pos["arguments"].append(arg)
    sign = {1: "+1", 0: "0", -1: "-1"}[payload["stance"]]
    collect.write("issue", path, issue, f"argue {path}#{pos['id']} {sign}", payload.get("reason", ""), ctx)
    return view(issue)


def link(collect, path: str, payload: dict, ctx) -> dict:
    """连一条 IBIS 边。payload: type, target, reason?"""
    issue = collect.get("issue", path).body
    edge = IssueLink(type=payload["type"], target=payload["target"]).model_dump()
    if edge not in issue["links"]:
        issue["links"].append(edge)
        collect.write("issue", path, issue, f"link {path} {edge['type']} {edge['target']}", payload.get("reason", ""), ctx)
    return view(issue)


def spawn(collect, path: str, payload: dict, ctx) -> dict:
    """为验证某个立场派出一个 work(只记 id)。payload: position, work_id, reason?"""
    issue = collect.get("issue", path).body
    pos = _position(issue, payload["position"])
    if payload["work_id"] not in pos["spawned_works"]:
        pos["spawned_works"].append(payload["work_id"])
        collect.write("issue", path, issue, f"spawn {path}#{pos['id']} -> {payload['work_id']}", payload.get("reason", ""), ctx)
    return view(issue)


def decide(collect, path: str, payload: dict, ctx) -> dict:
    """争出结果:把某个立场写成一张卡。两个相邻提交:[issue] decide + [card] write,同一个 Decision trailer。
    payload: position, card (卡的 path), title?, body?, context?, reason?"""
    from services.collect import CollectError
    issue = collect.get("issue", path).body
    pos = _position(issue, payload["position"])
    card_path = payload["card"]
    if collect.exists("card", card_path):
        raise CollectError("exists", f"卡已存在:{card_path}", 409)
    decision = "dec_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)
    trailer = f"Decision: {decision}"
    before = dict(issue)
    issue["card"] = card_path
    collect.write("issue", path, issue, f"decide {path}#{pos['id']} -> card {card_path}", payload.get("reason", ""), ctx,
                  extra_trailer=trailer)
    card = {"title": payload.get("title") or pos["claim"], "body": payload.get("body") or pos["claim"],
            "context": payload.get("context", ""), "links": [], "issue": path}
    try:
        collect.create("card", card_path, card, payload.get("reason", ""), ctx, extra_trailer=trailer)
    except Exception:
        collect.write("issue", path, before, f"revert decide {path}#{pos['id']}", "card 没写成,退回", ctx,
                      extra_trailer=trailer)
        raise
    return view(issue)


def read_view(collect, path: str, obj: dict) -> dict:
    return view(obj)


LAYER = LayerSpec(
    name="issue", format="json", model=Issue, title="question", builtin=True,
    refs={"card": "card"},
    behaviors={"position": position, "argue": argue, "link": link, "spawn": spawn, "decide": decide},
    description="议事:一个问题 + 立场 + 论证 + IBIS 边。立场 / 论证只增不改。目录下的 manager.json 决定谁管它。",
)
LAYER.fields = fields_of(Issue, LAYER.refs)
LAYER.view = read_view  # type: ignore[attr-defined]

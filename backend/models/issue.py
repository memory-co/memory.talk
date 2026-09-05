"""issue —— 一个问题 + 立场 + 论证(IBIS),有人管、能派活(docs/works/v5/issue.md)。

文件形态:issues/<issue_id>.json。立场与论证只增不改(由 service 保证,git 兜底)。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .card import Origin

Stance = Literal[1, 0, -1]
LinkType = Literal["specializes", "suggested_by", "questions", "replaces", "related"]


class Argument(BaseModel):
    id: str
    stance: Stance = Field(description="+1 支持 / 0 中立 / -1 反对")
    comment: str = ""
    evidence: Origin | None = Field(None, description="证据:哪个 task 的哪些 round")
    task_id: str | None = Field(None, description="若来自派出的论证 task,记它的 id")
    created_at: str


class Position(BaseModel):
    id: str
    claim: str
    origin: Origin | None = None
    arguments: list[Argument] = Field(default_factory=list)
    spawned_tasks: list[str] = Field(default_factory=list, description="为验证这个立场派出的 task")
    created_at: str


class IssueLink(BaseModel):
    type: LinkType
    target: str = Field(description="对端 issue id;suggested_by 也可指 <issue_id>#<position_id>")


class Issue(BaseModel):
    id: str
    question: str
    origin: Origin | None = Field(None, description="从哪个 task 的哪些 round 冒出来")
    manager_task: str | None = Field(None, description="树上管它的 task;None = 还没人管")
    card: str | None = Field(None, description="争完写成的卡(card id);也可能是「挂在哪张卡上当讨论页」")
    positions: list[Position] = Field(default_factory=list)
    links: list[IssueLink] = Field(default_factory=list)
    created_at: str


# ---- 读视图:附现算的计数 ----

class PositionView(Position):
    up: int = 0
    down: int = 0
    neutral: int = 0
    credence: int = Field(0, description="up - down,现算,不存")


class IssueView(Issue):
    positions: list[PositionView] = Field(default_factory=list)


class IssueSummary(BaseModel):
    id: str
    question: str
    manager_task: str | None = None
    card: str | None = None
    position_count: int = 0


# ---- 写请求 ----

class IssueCreate(BaseModel):
    question: str
    origin: Origin | None = None
    manager_task: str | None = None
    reason: str = ""


class PositionCreate(BaseModel):
    claim: str
    origin: Origin | None = None
    reason: str = ""


class ArgumentCreate(BaseModel):
    stance: Stance
    comment: str = ""
    evidence: Origin | None = None
    task_id: str | None = None
    reason: str = ""


class ManagerBind(BaseModel):
    task_id: str | None = Field(description="绑到哪个 task;null = 解绑")
    reason: str = ""


class LinkCreate(BaseModel):
    type: LinkType
    target: str
    reason: str = ""


class SpawnTask(BaseModel):
    task_id: str = Field(description="为这个立场派出的 task(task 层未实现,先记 id)")
    reason: str = ""


class WriteCard(BaseModel):
    """争出结果:把某个立场写成一张卡。issue 记结论 + card 建正文,同一个 commit。"""
    position_id: str
    title: str
    body: str = ""
    dir: str = ""
    slug: str | None = None
    context: str = ""
    reason: str = ""


class OpenDiscussion(BaseModel):
    """对一张卡不同意:开一个 issue 挂到它身上当讨论页。同一个 commit。"""
    question: str
    origin: Origin | None = None
    manager_task: str | None = None
    reason: str = ""

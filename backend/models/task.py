"""task —— 把一件事做下去的载体,复杂的事是一棵树(docs/works/v5/task.md)。全部是裸文件。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .server import HandleInfo, Window

TaskStatus = Literal["todo", "doing", "done", "abandoned"]


class Task(BaseModel):
    id: str
    goal: str = Field(description="它是什么事(一句话)")
    project: str = Field("", description="在哪个项目(工作目录)")
    parent: str | None = Field(None, description="属于哪件更大的事")
    status: TaskStatus = "todo"
    created_at: str
    done_at: str | None = None


class TaskCreate(BaseModel):
    goal: str
    project: str = ""
    parent: str | None = None


class TaskUpdate(BaseModel):
    goal: str | None = None
    project: str | None = None
    status: TaskStatus | None = None


class TaskNode(Task):
    children: list["TaskNode"] = Field(default_factory=list)


# ---- 画布:task 的视图,可随时重排 ----

class Panel(BaseModel):
    id: str
    uri: str
    member: str | None = Field(None, description="装的是哪个成员(终端类块必有;浏览器 / 文件类可无)")
    x: int
    y: int
    w: int
    h: int


class Canvas(BaseModel):
    cols: int = 24
    rows: int = 16
    version: int = 0
    panels: list[Panel] = Field(default_factory=list)


class CanvasPut(BaseModel):
    version: int = Field(description="乐观锁:必须等于当前 version")
    panels: list[Panel]


# ---- 成员:现场,身份脱离布局 ----

class Member(BaseModel):
    id: str
    uri: str
    scheme: str
    server: str
    cwd: str | None = None
    created_at: str
    last_attached: str


class MemberCreate(BaseModel):
    uri: str


class MemberView(Member):
    alive: bool = False
    window: Window | None = None
    handle: HandleInfo | None = None


# ---- 痕迹 ----

class Round(BaseModel):
    id: str
    timestamp: str | None = None
    role: str                       # human / assistant / tool / system
    text: str


class Event(BaseModel):
    ts: str
    type: str
    data: dict = Field(default_factory=dict)


TaskNode.model_rebuild()

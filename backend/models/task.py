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
    session: str | None = Field(None, description="装的是哪个会话(终端类块必有;浏览器 / 文件类可无)")
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


# ---- 会话:现场,身份脱离布局 ----

class Session(BaseModel):
    id: str
    uri: str
    scheme: str
    server: str = Field(description="建它的 server(https → http,vim → default)")
    cwd: str | None = None
    created_at: str
    last_attached: str


class SessionCreate(BaseModel):
    uri: str


class SessionView(Session):
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


# ---- 成员:人 ↔ task。只做可见性,不做权限(整个实例给一个团队用) ----

class Member(BaseModel):
    user: str = Field(description="团队里的一个人,由客户端在请求头 X-Memory-Talk-User 里自报")
    first_seen: str
    last_seen: str
    ops: int = Field(0, description="对这个 task 的操作次数")


class MemberView(Member):
    active: bool = Field(False, description="最近一段时间内操作过 = 当前正在操作(现算)")


class Members(BaseModel):
    current: list[MemberView] = Field(default_factory=list, description="当前正在操作的人")
    history: list[MemberView] = Field(default_factory=list, description="历史操作过的人(含当前),按最近活动倒序")

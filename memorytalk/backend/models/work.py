"""work —— 把一件事做下去的载体,复杂的事是一棵树(docs/designs/v5/work.md)。全部是裸文件。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .work_server import HandleInfo, Window

WorkStatus = Literal["todo", "doing", "done", "abandoned"]


class Work(BaseModel):
    id: str
    goal: str = Field(description="它是什么事(一句话)")
    created_by: str | None = Field(None, description="谁建的(归属,建时定下不改;不是权限)")
    parent: str | None = Field(None, description="属于哪件更大的事")
    status: WorkStatus = "todo"
    created_at: str
    done_at: str | None = None


class WorkCreate(BaseModel):
    goal: str
    parent: str | None = None


class WorkUpdate(BaseModel):
    goal: str | None = None
    status: WorkStatus | None = None


class WorkNode(Work):
    children: list["WorkNode"] = Field(default_factory=list)


# ---- 画布:work 的视图,可随时重排 ----

class Panel(BaseModel):
    session: str = Field(description="装的是哪个会话;一个会话最多出现在一个格子里")
    collapsed: bool = Field(False, description="收起 = 只剩标题行")


class Column(BaseModel):
    id: str = Field(description="前端自定,画布内唯一")
    panels: list[Panel] = Field(default_factory=list, description="从上到下")


class Canvas(BaseModel):
    """布局 = 几列,每列从上到下摆会话。默认一列;会话开了就进第一列的末尾,关了就从格子里拿掉。"""
    version: int = 0
    columns: list[Column] = Field(default_factory=list)


class CanvasPut(BaseModel):
    version: int = Field(description="乐观锁:必须等于当前 version")
    columns: list[Column]


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
    server: str = Field("", exclude=True)          # 内部寻址用,不对外
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


WorkNode.model_rebuild()


# ---- user ↔ work:谁动过。只做可见性,不做权限(整个实例给一个团队用) ----

class WorkUser(BaseModel):
    user: str = Field(description="团队里的一个人,由客户端在请求头 X-Memory-Talk-User 里自报")
    first_seen: str
    last_seen: str
    ops: int = Field(0, description="对这个 work 的操作次数")


class WorkUserView(WorkUser):
    active: bool = Field(False, description="最近一段时间内操作过 = 当前正在操作(现算)")


class WorkUsers(BaseModel):
    current: list[WorkUserView] = Field(default_factory=list, description="当前正在操作的人")
    history: list[WorkUserView] = Field(default_factory=list, description="历史操作过的人(含当前),按最近活动倒序")

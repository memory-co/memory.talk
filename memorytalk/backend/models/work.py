"""work —— 把一件事做下去的载体,复杂的事是一棵树(docs/designs/v5/work.md)。全部是裸文件。"""
from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator

from .work_server import HandleInfo, Window

WorkStatus = Literal["running", "archived"]

# 旧的四档状态读进来时折成两档:还在做的都是 running,做完 / 放下的都是 archived。
_LEGACY_STATUS = {"todo": "running", "doing": "running", "done": "archived", "abandoned": "archived"}


class Work(BaseModel):
    id: str
    goal: str = Field(description="它是什么事(一句话)")
    created_by: str | None = Field(None, description="谁建的(归属,建时定下不改;不是权限)")
    parent: str | None = Field(None, description="属于哪件更大的事")
    status: WorkStatus = "running"
    created_at: str
    archived_at: str | None = Field(None, validation_alias=AliasChoices("archived_at", "done_at"))

    @field_validator("status", mode="before")
    @classmethod
    def _legacy_status(cls, v):
        return _LEGACY_STATUS.get(v, v)


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
    worklet: str = Field(description="装的是哪个工作单元;一个工作单元最多出现在一个格子里")
    collapsed: bool = Field(False, description="收起 = 只剩标题行")


class Column(BaseModel):
    """一列 = 固定编号 + 别名(work-events.md §3):id 写成 c<编号>,服务端发、永不改不复用;别名随便改、可空可重名。"""
    id: str = Field(description="c<编号>;服务端发,永不改、不复用")
    alias: str = Field("", max_length=80, validation_alias=AliasChoices("alias", "name"),
                       description="别名;空 = 前端显示「列 <编号>」。旧数据里叫 name")
    panels: list[Panel] = Field(default_factory=list, description="从上到下")
    collapsed: bool = Field(False, description="整列收起 = 缩成一条窄边")


class Canvas(BaseModel):
    """布局 = 几列,每列从上到下摆工作单元。至少一列;工作单元开的时候定在哪一列,关了就从格子里拿掉。
    不再整份覆盖:每个动作一个请求(work-events.md §2)。"""
    version: int = 0
    next_column: int = Field(0, description="下一列的编号;单调递增")
    columns: list[Column] = Field(default_factory=list)


class ColumnCreate(BaseModel):
    alias: str = Field("", max_length=80)
    beside: str | None = Field(None, description="挨着哪一列加;不给 = 加在最右")
    side: Literal["left", "right"] = "right"


class ColumnUpdate(BaseModel):
    alias: str | None = Field(None, max_length=80, description="改别名(编号不动)")
    collapsed: bool | None = None


class WorkletMove(BaseModel):
    column: str = Field(description="挪到哪一列(c<编号>)")
    index: int | None = Field(None, ge=0, description="列里从上数第几个;不给 = 放末尾")


class WorkletUpdate(BaseModel):
    collapsed: bool


# ---- 工作单元:现场,身份脱离布局 ----

class Worklet(BaseModel):
    id: str
    uri: str
    scheme: str
    server: str = Field(description="建它的 server(https → http,vim → default)")
    cwd: str | None = None
    created_at: str
    last_attached: str


class WorkletCreate(BaseModel):
    uri: str
    column: str | None = Field(None, description="放进哪一列(c<编号>);不给 = 最左一列")


class WorkletView(Worklet):
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

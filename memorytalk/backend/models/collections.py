"""Collections —— 认知层的容器(docs/designs/v5/collections.md)。

对象 = 一个带后缀的目录 `<path>.<layer>/`,里面是一组文件;一次写 = 一批文件改动,交给层的 check 过 / 不过;origin 是任何不带后缀的文件。
一个对象的 id 就是它的 path(不含后缀),标题就是末段。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LayerInfo(BaseModel):
    name: str
    order: int = Field(description="0 = 最底层(origin)")
    builtin: bool = Field(description="False = 用户层:<home>/layers/<name>.yaml")
    suffix: str | None = Field(description="对象目录后缀 `.<name>`;origin 为 None(不带后缀的一切)")
    description: str = ""
    protocol: dict = Field(description="这一层的协议(object 规则 + files 每种文件的 pattern / example / fixed / required / format / template);前端据此画表单")


class TreeView(BaseModel):
    path: str
    layer: str | None = Field(None, description="在某个对象目录里时:那一层")
    items: list["TreeItem"] = Field(default_factory=list)
    can_create: dict = Field(default_factory=dict, description="这里还能建什么:objects[](按层)+ files[](按这一层的文件种类)")
    candidate: dict | None = Field(None, description="带 candidate= 时:这个名字行不行")


class CheckResult(BaseModel):
    ok: bool
    reason: str | None = None


class Obj(BaseModel):
    layer: str
    path: str = Field(description="对象 id = 路径(不含后缀);标题就是它的末段")
    title: str
    files: dict[str, str] = Field(default_factory=dict, description="目录里的文件 {相对路径: 内容};origin 为空")
    content: str | None = Field(None, description="origin:原文")


class ObjWrite(BaseModel):
    files: dict[str, str | None] | None = Field(None, description="目录里的文件 {相对路径: 内容};改时 null = 删、没提到的不动。整批交给层的 check")
    content: str | None = Field(None, description="origin:原文")
    subject: str | None = Field(None, description="提交信息的主题;不给就是 write / edit <path>")
    reason: str = ""


class Revision(BaseModel):
    sha: str
    author: str
    date: str
    subject: str
    body: str = ""


class SearchHit(BaseModel):
    layer: str
    path: str = Field(description="对象 path(origin 为文件路径)")
    file: str
    line: int
    text: str


class CatalogEntry(BaseModel):
    path: str
    title: str


class CatalogDir(BaseModel):
    dir: str
    objects: list[CatalogEntry] = Field(default_factory=list)
    subdirs: list["CatalogDir"] = Field(default_factory=list)


class TreeItem(BaseModel):
    name: str
    path: str = Field(description="仓库内路径;对象为不含后缀的 path")
    kind: Literal["dir", "file", "object"]
    layer: str | None = Field(None, description="object / file 属于哪层")


class Manager(BaseModel):
    dir: str = Field(description="manager.json 所在目录('' = 根)")
    work: str


class ManagerPut(BaseModel):
    work: str
    reason: str = ""


class InboxItem(BaseModel):
    ts: str
    layer: str
    path: str
    subject: str
    sha: str | None = None
    by: str | None = None
    routed_by: str = Field(description="哪个 manager.json 把它路由过来的(目录,'' = 根)")


CatalogDir.model_rebuild()

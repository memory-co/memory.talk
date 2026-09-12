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
    builtin: bool
    suffix: str | None = Field(description="对象目录后缀 `.<name>`;origin 为 None(不带后缀的一切)")
    files: list[str] = Field(default_factory=list, description="目录里允许的文件(可通配);origin 为空(文件本身)")
    schema_: dict | None = Field(None, alias="schema", description="用户层的 YAML(原样);内置层为 null,规则在代码里")
    description: str = ""

    model_config = {"populate_by_name": True}


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


class LayerCreate(BaseModel):
    name: str
    schema_yaml: str = Field(description="层的 YAML:files 清单(每个文件的 format / required / append_only / fields),见 docs/designs/v5/collections-layer.md")
    reason: str = ""


CatalogDir.model_rebuild()

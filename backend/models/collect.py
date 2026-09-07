"""Collect —— 认知层的容器(docs/works/v5/collect.md)。

对象 = 一个带后缀的目录 `<path>.<layer>/`,本体文件在里面;origin 是任何不带后缀的文件。
一个对象的 id 就是它的 path(不含后缀)。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FieldSpec(BaseModel):
    type: str = Field(description="string / int / bool / list[string] / ref / list[ref] / object(内置层才有)")
    required: bool = False
    ref: str | None = Field(None, description="type 为 ref 时指向哪个 layer")
    description: str = ""


class LayerInfo(BaseModel):
    name: str
    order: int = Field(description="0 = 最底层(origin)")
    builtin: bool
    suffix: str | None = Field(description="对象目录后缀 `.<name>`;origin 为 None(不带后缀的一切)")
    body: str | None = Field(description="本体文件名;origin 为 None(文件本身)")
    format: Literal["json", "markdown", "raw"]
    title: str | None = Field(None, description="哪个字段是标题(目录 / 召回用)")
    fields: dict[str, FieldSpec] = Field(default_factory=dict)
    behaviors: list[str] = Field(default_factory=list, description="schema 之上的领域动作;用户层为空")
    description: str = ""


class Obj(BaseModel):
    layer: str
    path: str = Field(description="对象 id = 路径(不含后缀)")
    title: str | None = None
    body: Any = Field(description="按 layer 的 schema 解析后的对象;origin 为原文字符串")


class ObjCreate(BaseModel):
    data: dict[str, Any] | None = Field(None, description="按 layer schema 的字段(非 origin)")
    content: str | None = Field(None, description="origin:原文")
    reason: str = ""


class ObjUpdate(BaseModel):
    data: dict[str, Any] | None = Field(None, description="要改的字段(合并);markdown 层的正文用 `body` 键")
    content: str | None = None
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
    task: str


class ManagerPut(BaseModel):
    task: str
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
    schema_yaml: str = Field(description="schemas/<name>.yaml 的内容,见 docs/works/v5/collect-layer.md")
    reason: str = ""


CatalogDir.model_rebuild()

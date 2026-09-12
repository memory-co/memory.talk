"""Collections —— 认知层的容器(docs/designs/v5/collections.md)。

对象 = 一个带后缀的目录 `<path>.<layer>/`,里面是一组文件,允许哪些文件由层的 schema 定;origin 是任何不带后缀的文件。
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


class FileInfo(BaseModel):
    pattern: str = Field(description="对象目录内的相对路径;可用 * 通配")
    format: Literal["markdown", "markdown+frontmatter", "yaml", "json", "text"]
    required: bool = False
    fields: dict[str, FieldSpec] = Field(default_factory=dict, description="yaml / json / frontmatter 的字段")
    description: str = ""


class LayerInfo(BaseModel):
    name: str
    order: int = Field(description="0 = 最底层(origin)")
    builtin: bool
    suffix: str | None = Field(description="对象目录后缀 `.<name>`;origin 为 None(不带后缀的一切)")
    title: str = Field("dirname", description="标题从哪来:dirname 或 <文件>:<字段>")
    files: list[FileInfo] = Field(default_factory=list, description="目录里允许的文件;origin 为空(文件本身)")
    behaviors: list[str] = Field(default_factory=list, description="schema 之上的快捷动作;用户层为空")
    description: str = ""


class Obj(BaseModel):
    layer: str
    path: str = Field(description="对象 id = 路径(不含后缀)")
    title: str | None = None
    files: list[str] = Field(default_factory=list, description="目录里有哪些文件(相对路径);origin 为空")
    body: Any = Field(description="按 layer 的 schema 解析后的视图;origin 为原文字符串")


class ObjCreate(BaseModel):
    files: dict[str, str] | None = Field(None, description="目录里的文件 {相对路径: 内容};整目录按层的 schema 校验")
    data: dict[str, Any] | None = Field(None, description="简写:只有一个带字段文件的层(card 等),按字段写那个文件")
    content: str | None = Field(None, description="origin:原文")
    reason: str = ""


class ObjUpdate(BaseModel):
    files: dict[str, str | None] | None = Field(None, description="改 / 加 / 删(null)目录里的文件;没提到的不动")
    data: dict[str, Any] | None = Field(None, description="简写:字段合并(markdown 正文用 `body` 键)")
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
    schema_yaml: str = Field(description="层的 schema YAML(files 清单或单文件简写),见 docs/designs/v5/collections-layer.md")
    reason: str = ""


CatalogDir.model_rebuild()

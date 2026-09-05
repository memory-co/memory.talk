"""card —— 维基式的事实条目(docs/works/v5/card.md)。

一张卡 = 标题 + 正文 + 语境 + 链接;没有分数、没有状态位(只有「在 / 废弃」)。
文件形态是 markdown + 简单 frontmatter,id 就是仓库内相对路径(不含 .md):
    cards/<dir>/<slug>.md  →  id = "<dir>/<slug>"
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CardStatus = Literal["active", "deprecated"]


class Card(BaseModel):
    id: str = Field(description="仓库内相对路径(不含 .md),目录即目录分类")
    title: str
    body: str = ""
    context: str = Field("", description="在哪成立:关于哪个项目 / 用户 / 场景(本地论)")
    links: list[str] = Field(default_factory=list, description="相关卡的 id(内链)")
    issue: str | None = Field(None, description="讨论页:挂在这张卡上的 issue id")
    status: CardStatus = "active"


class CardCreate(BaseModel):
    title: str
    body: str = ""
    dir: str = Field("", description="放在哪个目录(分类);空 = 根")
    slug: str | None = Field(None, description="文件名;缺省由标题生成")
    context: str = ""
    links: list[str] = Field(default_factory=list)
    reason: str = Field("", description="为什么写这张卡(进 commit message)")
    origin: "Origin | None" = None


class CardUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    context: str | None = None
    links: list[str] | None = None
    reason: str = Field("", description="为什么改(进 commit message)")
    origin: "Origin | None" = None


class Origin(BaseModel):
    """出处:哪个 task 的哪些 round。task 层未实现,这里只记 id。"""
    task_id: str
    rounds: list[int] = Field(default_factory=list)


class CatalogEntry(BaseModel):
    id: str
    title: str
    status: CardStatus = "active"


class CatalogDir(BaseModel):
    dir: str
    cards: list[CatalogEntry] = Field(default_factory=list)
    subdirs: list["CatalogDir"] = Field(default_factory=list)


class Revision(BaseModel):
    sha: str
    author: str
    date: str
    subject: str
    body: str = ""


class SearchHit(BaseModel):
    kind: Literal["card", "issue"]
    id: str
    path: str
    line: int
    text: str


CardCreate.model_rebuild()
CardUpdate.model_rebuild()

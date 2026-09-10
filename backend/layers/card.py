"""card —— 记事层:维基式事实条目(docs/designs/v5/card.md)。对象 = `<path>.card/card.md`。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ._spec import LayerSpec, fields_of


class Card(BaseModel):
    title: str
    context: str = Field("", description="在哪成立:关于哪个项目 / 用户 / 场景")
    links: list[str] = Field(default_factory=list, description="相关卡的 path(内链)")
    issue: str | None = Field(None, description="讨论页:挂在这张卡上的 issue 的 path")
    body: str = ""


def discuss(collections, path: str, payload: dict, ctx) -> dict:
    """对这张卡不同意:开一个 issue 挂上去当讨论页。两个相邻提交:[issue] raise + [card] link。
    payload: issue (issue 的 path), question, origin?, reason?"""
    from layers.issue import Issue
    from services.collections import CollectionsError
    card = collections.get("card", path).body
    issue_path = payload["issue"]
    if collections.exists("issue", issue_path):
        raise CollectionsError("exists", f"issue 已存在:{issue_path}", 409)
    issue = Issue(question=payload["question"], origin=payload.get("origin"), card=path).model_dump()
    trailer = f"Discussion: {path}"
    collections.create("issue", issue_path, issue, payload.get("reason", ""), ctx, subject=f"raise {issue_path}: {issue['question'][:60]}",
                   extra_trailer=trailer)
    card["issue"] = issue_path
    collections.write("card", path, card, f"link {path} -> issue {issue_path}", payload.get("reason", ""), ctx, extra_trailer=trailer)
    return collections.get("issue", issue_path).body


LAYER = LayerSpec(
    name="card", format="markdown", model=Card, title="title", builtin=True,
    refs={"issue": "issue", "links": "card"},
    behaviors={"discuss": discuss},
    description="记事:一条事实,像维基词条。可改、可删,历史在 git。没有分数、没有状态位。",
)
LAYER.fields = fields_of(Card, LAYER.refs)

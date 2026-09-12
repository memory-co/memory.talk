"""card —— 记事层:维基式事实条目(docs/designs/v5/card.md)。对象 = `<path>.card/` 目录,里面只有 `card.md`(markdown + frontmatter)。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ._spec import FileRule, LayerSpec, fields_of


class Card(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    context: str = Field("", description="在哪成立:关于哪个项目 / 用户 / 场景")
    links: list[str] = Field(default_factory=list, description="相关卡的 path(内链)")
    issue: str | None = Field(None, description="讨论页:这张卡对应的 issue 的 path(卡记 issue,issue 不记卡)")
    body: str = ""


def discuss(collections, path: str, payload: dict, ctx) -> dict:
    """对这张卡不同意:开一个 issue,卡的 issue 字段指过去。两个提交:[issue] write + [card] link。
    payload: issue (issue 的 path), readme?, reason?"""
    from memorytalk.backend.services.collections import CollectionsError
    card = collections.get("card", path).body
    issue_path = payload["issue"]
    if collections.exists("issue", issue_path):
        raise CollectionsError("exists", f"issue 已存在:{issue_path}", 409)
    reason = payload.get("reason", "")
    collections.create("issue", issue_path, {"readme.md": payload.get("readme", "")}, reason, ctx)
    card["issue"] = issue_path
    collections.put("card", path, {"card.md": CARD_FILE.serialize(card)}, reason, ctx,
                    subject=f"link {path} -> issue {issue_path}")
    return collections.get("card", path).body


CARD_FILE = FileRule("card.md", "markdown+frontmatter", required=True, model=Card,
                     description="frontmatter:title / context / links / issue;正文是内容")
CARD_FILE.fields = fields_of(Card, {"issue": "issue", "links": "card"})

LAYER = LayerSpec(
    name="card", files=[CARD_FILE], title="card.md:title", builtin=True,
    refs={"issue": "issue", "links": "card"},
    behaviors={"discuss": discuss},
    description="记事:一条事实,像维基词条。可改、可删,历史在 git。没有分数、没有状态位。",
)

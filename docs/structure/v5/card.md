# Card

记事层:一条事实,像维基的一个词条。markdown + 简单 frontmatter,住在 git 仓库里;**可以改,历史在 git**。机制见 [`../../works/v5/card.md`](../../works/v5/card.md)。

## Schema

```json
{
  "id": "memory.talk/配置只来自环境变量",
  "title": "配置只来自环境变量",
  "body": "只用环境变量。配置文件是多出来的一份状态,要同步。",
  "context": "memory.talk v5",
  "links": ["memory.talk/Python-3.12"],
  "issue": "iss_202609052246183f6a",
  "status": "active"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | **仓库内相对路径**(不含 `.md`);目录即分类。建卡时由 `dir` + `slug`(缺省由 `title` 生成)拼成,之后不变 |
| `title` | string | 维基式规范标题——它出现在目录里,召回靠它 |
| `body` | string | 正文,可以比一句话长;但**一张卡讲一件事** |
| `context` | string | 在哪成立:关于哪个项目 / 用户 / 场景。「本地论」在卡上的落法——不是治理字段,是事实陈述的一部分 |
| `links[]` | string[] | 相关卡的 id(内链,只有一种类型) |
| `issue` | string \| null | 讨论页:挂在这张卡上的 issue |
| `status` | `active` \| `deprecated` | 唯一的状态位;废弃不删文件,目录默认不列 |

**没有的东西**:顶踩、可信度、沉浮、分数、版本号。对错在 issue 上争,历史在 git 里翻。

## slug 规则

`title` 去首尾空白,把空白和 `/ \ : * ? " < > | #` 折成 `-`,首尾去 `-`;空则 `untitled`。中文原样保留(`配置只来自环境变量`)。可显式传 `slug` 覆盖。

## 读视图

- **目录 `CatalogDir`**:`{"dir": "", "cards": [{"id","title","status"}], "subdirs": [CatalogDir]}`,按目录树嵌套;默认不含 `deprecated`。
- **召回文本**:目录渲染成缩进列表 `- <title>  (<id>)`,给 agent 直接读。
- **历史 `Revision[]`**:`{"sha","author","date","subject","body"}`,来自 `git log -- cards/<id>.md`。
- **检索 `SearchHit[]`**:`{"kind":"card","id","path","line","text"}`,来自 `git grep`。

## 存储

`memory/cards/<dir>/<slug>.md`:

```markdown
---
title: 配置只来自环境变量
context: memory.talk v5
links: memory.talk/Python-3.12
issue: iss_202609052246183f6a
status: deprecated
---

只用环境变量。配置文件是多出来的一份状态,要同步。
```

frontmatter 只有 `key: value` 行,不用 yaml 库;`links` 逗号分隔;`status` 只在非 `active` 时写。每个写动作一个 commit:

```
card: write <id>        建(body: Reason: / Task: / Rounds:)
card: edit <id>         改
card: deprecate <id>    废弃
decide: … -> card <id>  从 issue 写出来(与 issue 同一 commit)
discuss: card <id> -> … 对它开讨论页(与 issue 同一 commit)
```

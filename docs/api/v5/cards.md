# Cards API

card = 一条事实,维基式词条。可改、历史在 git;没有分数。字段见 [`../../structure/v5/card.md`](../../structure/v5/card.md)。

`card_id` 是仓库内相对路径(`memory.talk/配置只来自环境变量`),路径段直接放在 URL 里(`/api/cards/memory.talk/配置只来自环境变量`)。**固定子路径先于通配**:`/api/cards/recall`、`/api/cards/search` 是端点,不是卡;卡的 id 别叫这两个名字。

---

## GET /api/cards

目录:按目录分层的标题清单。召回注入的就是它。

| 参数 | 说明 |
|---|---|
| `dir` | 只看这个目录之下 |
| `include_deprecated` | 默认 `false` |

```json
{"dir": "", "cards": [],
 "subdirs": [{"dir": "memory.talk",
              "cards": [{"id": "memory.talk/配置只来自环境变量", "title": "配置只来自环境变量", "status": "active"}],
              "subdirs": []}]}
```

## GET /api/cards/recall

同上,渲染成 `text/plain`,给 agent 直接读。`dir` 参数同。

## GET /api/cards/search

`git grep -n -i` 词条文件。

| 参数 | 说明 |
|---|---|
| `q` | 必填;字面匹配,大小写不敏感 |

```json
[{"kind": "card", "id": "memory.talk/配置只来自环境变量", "path": "cards/memory.talk/配置只来自环境变量.md",
  "line": 8, "text": "只用环境变量。配置文件是多出来的一份状态,要同步。"}]
```

## POST /api/cards

写一张卡。

```json
{"title": "配置只来自环境变量", "body": "只用环境变量。", "dir": "memory.talk", "slug": null,
 "context": "memory.talk v5", "links": [], "reason": "写 config.py 时定的", "origin": {"task_id": "task_a", "rounds": [3]}}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | 是 | 维基式规范标题 |
| `body` | 否 | 正文 |
| `dir` | 否 | 放哪个目录;空 = 根 |
| `slug` | 否 | 文件名;缺省由 `title` 生成(见 structure 的 slug 规则) |
| `context` | 否 | 在哪成立 |
| `links` | 否 | 相关卡 id |
| `reason` / `origin` | 否 | 进 commit message |

**201** 返回 Card。副作用:`cards/<dir>/<slug>.md` + commit `card: write <id>`。

| 错误 | 状态 |
|---|---|
| id 已存在 | 409 `exists` |

## GET /api/cards/{card_id}

```json
{"id": "memory.talk/配置只来自环境变量", "title": "配置只来自环境变量", "body": "…", "context": "memory.talk v5",
 "links": [], "issue": "iss_…", "status": "active"}
```

| 参数 | 说明 |
|---|---|
| `rev` | git sha(来自 `/history`);读那个版本 |

不存在(或该 sha 下不存在)→ 404。

## PUT /api/cards/{card_id}

改卡。旧内容进历史,不另起一张。

```json
{"title": null, "body": "只用环境变量。配置文件是多出来的一份状态,要同步。", "context": null, "links": null, "reason": "补理由"}
```

四个内容字段都可选,`null` = 不动。返回 Card;commit `card: edit <id>`。

## DELETE /api/cards/{card_id}

废弃:`status → deprecated`,文件留着,目录默认不列。

| 参数 | 说明 |
|---|---|
| `reason` | 可选 |

返回 Card;commit `card: deprecate <id>`。

## GET /api/cards/{card_id}/history

```json
[{"sha": "527e8ae…", "author": "memory.talk", "date": "2026-09-05T22:46:19+00:00", "subject": "card: edit memory.talk/配置只来自环境变量", "body": "Reason: 补理由"},
 {"sha": "487d55f…", "author": "memory.talk", "date": "…", "subject": "decide: iss_…#p2 -> card memory.talk/配置只来自环境变量", "body": "Reason: …"}]
```

新在前。最多 50 条。

## POST /api/cards/{card_id}/issue

对这张卡不同意:新建一个 issue 挂到卡上当讨论页。**issue + card 同一个 commit**(`discuss: card <id> -> <issue_id>: <question>`)。

```json
{"question": "要不要升 3.13?", "origin": null, "manager_task": null, "reason": ""}
```

**201** 返回 IssueView(`card` 指回这张卡);卡的 `issue` 字段指向新 issue。

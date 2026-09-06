# Issues API

issue = 问题 + 立场 + 论证,IBIS 结构;有人管、能派活。字段见 [`../../structure/v5/issue.md`](../../structure/v5/issue.md)。所有写动作各自一个 commit,历史见 `/history`。

---

## GET /api/issues

清单。标注时「指认既有问题」查的就是它。

| 参数 | 说明 |
|---|---|
| `manager_task` | 只看这个 task 管的 |
| `unmanaged` | `true` = 只看还没人管的 |

```json
[{"id": "iss_…", "question": "memory.talk v5 的配置该走文件还是环境变量?", "manager_task": "task_root",
  "card": "memory.talk/配置只来自环境变量", "position_count": 2}]
```

## GET /api/issues/search

`git grep` 问题 / 立场 / 论证(整个 `issues/` 目录的 JSON 文本)。参数 `q`。返回 `SearchHit[]`,`kind: "issue"`。

## POST /api/issues

提一个问题。

```json
{"question": "…", "origin": {"task_id": "task_a", "rounds": [3, 4]}, "manager_task": null, "reason": "写 config.py 时撞见的"}
```

**201** 返回 IssueView(`positions: []`,`manager_task` 可为 `null` = 还没人管)。commit `issue: raise <id>: <question>`。

## GET /api/issues/{issue_id}

读视图:立场附现算 `up` / `down` / `neutral` / `credence`,按 `credence` 倒序。完整例子见 structure。404 `not_found`。

## GET /api/issues/{issue_id}/history

`Revision[]`,新在前——就是辩论序列。

## POST /api/issues/{issue_id}/positions

加一个立场。只增不改。

```json
{"claim": "只用环境变量,不要配置文件", "origin": null, "reason": ""}
```

**201** 返回 IssueView。新立场 id = `p<n>`。commit `issue: position <id>#p2: <claim>`。

## POST /api/issues/{issue_id}/positions/{position_id}/arguments

表态。

```json
{"stance": 1, "comment": "试了一遍,环境变量够用", "evidence": {"task_id": "task_try", "rounds": [9]}, "task_id": "task_try", "reason": ""}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `stance` | 是 | `1` / `0` / `-1` |
| `comment` | 否 | |
| `evidence` | 否 | 证据在哪个 task 的哪些 round |
| `task_id` | 否 | 来自哪个派出的论证 task |

**201** 返回 IssueView。commit `issue: argue <id>#p2 +1`,body 带 `Task:` / `Rounds:`。position 不存在 → 404。

## POST /api/issues/{issue_id}/positions/{position_id}/tasks

为验证这个立场派出一个 task。task 层的建 task 走 `POST /api/tasks`;这里只在立场上记 id(去重)。

```json
{"task_id": "task_try", "reason": ""}
```

**201** 返回 IssueView。commit `issue: spawn <id>#p2 -> <task_id>`(已记过则不提交)。

## PUT /api/issues/{issue_id}/manager

绑 / 换 / 解绑 manager task。

```json
{"task_id": "task_root", "reason": ""}
```

`task_id: null` = 解绑。返回 IssueView。commit `issue: manage <id> by <task_id>` / `issue: unmanage <id>`。不校验 task 存不存在(裸 id 引用)。

## POST /api/issues/{issue_id}/links

```json
{"type": "specializes", "target": "iss_…", "reason": ""}
```

`type` ∈ `specializes` / `suggested_by` / `questions` / `replaces` / `related`;`target` 可写 `<issue_id>#<position_id>`。同 `(type, target)` 已存在则不重复、不提交。**201** 返回 IssueView。commit `issue: link <id> <type> <target>`。

## POST /api/issues/{issue_id}/card

争出结果:把某个立场写成一张卡。**issue 记 `card` + 新建卡,同一个 commit**(`decide: <id>#p2 -> card <card_id>`)。

```json
{"position_id": "p2", "title": "配置只来自环境变量", "body": "", "dir": "memory.talk", "slug": null,
 "context": "memory.talk v5", "reason": "环境变量够用,配置文件多一份状态"}
```

| 字段 | 说明 |
|---|---|
| `position_id` | 必填;不存在 → 404 |
| `title` | 必填 |
| `body` | 空则用立场的 `claim` |
| `dir` / `slug` / `context` | 同 `POST /api/cards` |

**201** 返回 IssueView(`card` 已填);新卡的 `issue` 指回来。卡 id 已存在 → 409 `exists`。

写卡不关闭 issue:立场继续竞争,翻盘了回来 `PUT /api/cards/{id}` 改卡。

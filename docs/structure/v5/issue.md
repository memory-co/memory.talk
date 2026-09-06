# Issue + Position + Argument + IssueLink

议事层:一个问题、它的立场、每个立场的论证、问题之间的 IBIS 边。一个 issue 一个 JSON 文件,住在 git 仓库里;**立场和论证只增不改**(service 保证,git 兜底)。机制见 [`../../works/v5/issue.md`](../../works/v5/issue.md)。

## Schema

`GET /api/issues/{id}` 的读视图——立场附现算计数、按 `credence` 倒序:

```json
{
  "id": "iss_202609052246183f6a",
  "question": "memory.talk v5 的配置该走文件还是环境变量?",
  "origin": {"task_id": "task_a", "rounds": [3, 4]},
  "manager_task": "task_root",
  "card": "memory.talk/配置只来自环境变量",
  "positions": [
    {
      "id": "p2", "claim": "只用环境变量,不要配置文件", "origin": null,
      "arguments": [
        {"id": "a1", "stance": 1, "comment": "试了一遍,环境变量够用",
         "evidence": {"task_id": "task_try", "rounds": [9]}, "task_id": "task_try",
         "created_at": "2026-09-05T22:46:18Z"}
      ],
      "spawned_tasks": ["task_try"],
      "created_at": "2026-09-05T22:46:18Z",
      "up": 1, "down": 0, "neutral": 0, "credence": 1
    },
    {
      "id": "p1", "claim": "加一个 settings.json", "origin": null,
      "arguments": [{"id": "a1", "stance": -1, "comment": "多一份状态要同步", "created_at": "…"}],
      "spawned_tasks": [], "created_at": "…",
      "up": 0, "down": 1, "neutral": 0, "credence": -1
    }
  ],
  "links": [{"type": "specializes", "target": "iss_2026090522…"}],
  "created_at": "2026-09-05T22:46:18Z"
}
```

## Issue 字段

| 字段 | 类型 | 改不改 | 说明 |
|---|---|---|---|
| `id` | string | 不改 | `iss_<时间戳><4hex>` |
| `question` | string | 不改 | 问题本身 |
| `origin` | Origin \| null | 不改 | 从哪个 task 的哪些 round 冒出来。**出处不是归属**——冒出它的 task 冻结了,issue 还活着 |
| `manager_task` | string \| null | 改 | 树上管它的 task;`null` = 还没人管(这是有用的状态) |
| `card` | string \| null | 改 | 两个含义,看谁先建:争出结果写成的卡(`POST …/card`),或这个 issue 挂在哪张卡上当讨论页(`POST /api/cards/{id}/issue`) |
| `positions[]` | Position[] | 只增 | |
| `links[]` | IssueLink[] | 只增 | 同 `(type, target)` 不重复 |
| `created_at` | ISO 8601 | 不改 | |

**Origin**:`{"task_id": "...", "rounds": [int, ...]}`。`rounds` 是 `rounds.jsonl` 里的下标(0 起),可空。task 层未必还在——读时不校验。

## Position 字段

| 字段 | 说明 |
|---|---|
| `id` | `p<n>`,issue 内顺序编号 |
| `claim` | 立场文本(候选答案) |
| `origin` | 这个立场从哪来(Origin \| null) |
| `arguments[]` | 只增 |
| `spawned_tasks[]` | 为验证这个立场派出的 task id;去重 |
| `created_at` | |

读视图多四个**现算**字段:`up` / `down` / `neutral` = `stance` 为 `+1` / `-1` / `0` 的论证数;`credence = up - down`。不存、不回写。

## Argument 字段

| 字段 | 说明 |
|---|---|
| `id` | `a<n>`,立场内顺序编号 |
| `stance` | `1` 支持 / `0` 中立 / `-1` 反对。`≠0` 的就是 IBIS Argument;`0` 是「相关但不站队」 |
| `comment` | 一句话 |
| `evidence` | Origin \| null:证据在哪个 task 的哪些 round |
| `task_id` | 若来自派出的论证 task,记它;与 `evidence.task_id` 可同可不同 |
| `created_at` | |

**沉默不算数**:没有论证就没有计数;`0` 也不进 credence。

## IssueLink

```json
{"type": "specializes", "target": "iss_…"}
```

| `type` | 含义 | 方向 |
|---|---|---|
| `specializes` | 本 issue 是 target 的更窄版(子问题) | 有向 |
| `suggested_by` | 本 issue 被 target 引出;target 可写 `<issue_id>#<position_id>`(答案引出新问题) | 有向 |
| `questions` | 本 issue 质疑 target 的前提 | 有向 |
| `replaces` | 本 issue 重述并取代 target(target 不删) | 有向 |
| `related` | 泛关联 | 无向(两边各记一条,或只记一边,读者自己对称) |

**issue 图和 task 树是两套层级**:task 树表达事怎么拆(有状态、有完成),issue 图表达问题怎么细化(没有)。别拿一个代替另一个。

## 存储

`memory/issues/<issue_id>.json`,pydantic dump、缩进 2、`exclude_none`。每个写动作一个 commit:

```
issue: raise <id>: <question[:60]>          建
issue: position <id>#p2: <claim[:60]>       加立场
issue: argue <id>#p2 +1                     表态(body 带 Task: / Rounds:)
issue: manage <id> by <task_id>             绑 manager   / issue: unmanage <id>
issue: link <id> specializes <target>       连边
issue: spawn <id>#p2 -> <task_id>           派活
decide: <id>#p2 -> card <card_id>           写卡(同一 commit 也动了 cards/…)
discuss: card <card_id> -> <id>: <question> 对卡开讨论页(同一 commit 也动了 cards/…)
```

commit body 里 `Reason:` 来自请求的 `reason`,`Task:` / `Rounds:` 来自 `origin` / `evidence`。历史 = `git log -- issues/<id>.json`。

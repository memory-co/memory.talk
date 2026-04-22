# Link

Link 是 memory.talk 中所有关联关系的统一结构。可以连接任意类型：card↔card、card↔session、session↔session。

## Schema

```json
{
  "link_id": "link_01jzq7rm",
  "source_id": "card_01jz8k2m",
  "source_type": "card",
  "target_id": "sess_abc123",
  "target_type": "session",
  "comment": "从这段讨论中提取",
  "ttl": 1209600,
  "created_at": "2026-04-16T10:30:00Z"
}
```

## 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `link_id` | string | 自动生成 | `link_<ULID>`，Link 自身的唯一标识 |
| `source_id` | string | 是 | 源对象 ID（`card_<ULID>` 或 `sess_<ULID>`） |
| `source_type` | string | 是 | `card` 或 `session`（冗余但方便 dispatch） |
| `target_id` | string | 是 | 目标对象 ID（格式同 source_id） |
| `target_type` | string | 是 | `card` 或 `session` |
| `comment` | string | 否 | 说明为什么关联 |
| `ttl` | integer | 自动 | 剩余生命值（秒）。`0` = 默认 link sentinel（跟随 parent card，不参与秒级计时），`>0` = 活跃用户 link，`<0` = 已过期用户 link |
| `created_at` | string | 自动生成 | 创建时间 |

方向由 source → target 表达。禁止 `source == target` 自环。

## Link 的两类来源

### 默认 link（`ttl = 0`）

card 写入时，服务端扫描 `rounds[].session_id`（展开后每条 round 里自带的字段），为每个不同的 session_id 自动生成一条 card → session 默认 link。写入者不传、不参与这个过程。

默认 link 的 `ttl` 恒为 `0`，含义是"不独立计时"——view 时永远随所属 card 一起返回，card 的 TTL <= 0 被遗忘时这条 link 一起遗忘，也**不会被 view 隐式续命**（续命对它无意义）。

### 用户 link（`ttl > 0`）

通过 [`link create`](../../cli/v2/link.md) 写入。创建时 `ttl` 取 `settings.ttl.link.initial`（默认 1209600 秒 = 14 天），被 view 命中时按 `ttl.link.factor` 续命，超时后独立过期（不影响两端对象）。

可连接任何类型组合：card↔card、card↔session、session↔session。

## TTL 遗忘机制

Link 和 Talk-Card 都通过 TTL 实现自然遗忘。

### 存储实现

数据库中存储的不是倒计时数字，而是一个**未来的时间戳**（`expires_at`）：

- **创建时**：`expires_at = now + initial`
- **被访问时**：`remaining = expires_at - now`，`expires_at = now + min(remaining * factor, max)`
- **读取时**：`ttl = expires_at - now`，自动计算剩余值返回给调用方

这样不需要定时任务去全局衰减。时间自然流逝就是衰减，访问就是续命。

默认 link（`ttl = 0`）**不存 `expires_at`**——它是 sentinel，读取逻辑直接短路返回 `ttl = 0` 并把这条 link 视为"有效"输出。

### 对外表现

调用方看到的 `ttl` 是 `expires_at - now` 算出来的**秒数**，表示还有多久会被遗忘：

| ttl | 含义 |
|-----|------|
| `> 0` | 活跃（用户 link），秒数。`view` 命中两端任一对象时按 `factor` 续命 |
| `= 0` | 默认 link sentinel——**不是 "0 秒"**，而是 "不参与秒级计时"。永远跟随 parent card 出现，card 被遗忘它一起遗忘，`view` 不续命 |
| `< 0` | 用户 link 已过期。`view` 仍返回（方便看"曾经指向过什么"），`search` 过滤掉。数据保留，不删除 |

### 什么时候刷新

- **view 命中 card** → 刷新该 card 的 ttl（用 `ttl.card.factor`），默认 link 不单独刷新。
- **view 命中一端是用户 link 的对象** → 该 link 的 ttl 被隐式刷新（用 `ttl.link.factor`）。

Card 和用户 link 的 ttl 独立刷新，使用各自在 settings.json 中配置的 factor 和 max。

常用的记忆和关联会被反复访问而续命，冷门的自然淡忘。这模拟了人类记忆的遗忘曲线——不是删除，是逐渐想不起来。

# Link

Link 是 memory.talk 中所有关联关系的统一结构。可以连接任意类型：card↔card、card↔session。

## Schema

```json
{
  "link_id": "01jzq7rm",
  "source_id": "01jz8k2m",
  "source_type": "card",
  "target_id": "abc123",
  "target_type": "session",
  "comment": "从这段讨论中提取",
  "ttl": 100,
  "created_at": "2026-04-16T10:30:00Z"
}
```

## 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `link_id` | string | 自动生成 | Link 自身的唯一标识（ULID） |
| `source_id` | string | 是 | 源对象 ID |
| `source_type` | string | 是 | `card` 或 `session` |
| `target_id` | string | 是 | 目标对象 ID |
| `target_type` | string | 是 | `card` 或 `session` |
| `comment` | string | 否 | 说明为什么关联 |
| `ttl` | integer | 自动 | 剩余生命值，创建时设为初始值（默认 100） |
| `created_at` | string | 自动生成 | 创建时间 |

方向由 source → target 表达。

## 不同场景下的使用

**`cards create` 时内嵌 link**：简写为 `{id, type, comment}`，source 隐含为当前 card，方向为当前 card → target。

**`links create` 独立创建**：完整写 `{source_id, source_type, target_id, target_type, comment}`，显式指定方向。

**`recall` / `cards get` 返回**：带完整字段包括 `link_id` 和 `ttl`，简写为 `{link_id, id, type, comment, ttl}`（id/type 为对方的 ID 和类型）。

## TTL 遗忘机制

Link 和 Talk-Card 都通过 TTL 实现自然遗忘。

### 存储实现

数据库中存储的不是倒计时数字，而是一个**未来的时间戳**（`expires_at`）：

- **创建时**：`expires_at = now + initial`
- **被访问时**：`remaining = expires_at - now`，`expires_at = now + min(remaining * factor, max)`
- **读取时**：`ttl = expires_at - now`，自动计算剩余值返回给调用方

这样不需要定时任务去全局衰减。时间自然流逝就是衰减，访问就是续命。

### 对外表现

调用方看到的 `ttl` 是一个计算后的值（如天数或小时数），表示还有多久会被遗忘：

- `ttl > 0`：活跃，出现在查询结果中
- `ttl <= 0`：遗忘，不再出现在查询结果中（数据保留，不删除）

### 什么时候刷新

- **recall 命中 card** → 刷新该 card 的 ttl（用 `ttl.card.factor`）
- **cards get --link-id** → 刷新该 link 的 ttl（用 `ttl.link.factor`）

Card 和 Link 的 ttl 独立刷新，使用各自在 settings.json 中配置的 factor 和 max。

常用的记忆和关联会被反复访问而续命，冷门的自然淡忘。这模拟了人类记忆的遗忘曲线——不是删除，是逐渐想不起来。

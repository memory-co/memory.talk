# Card 创建流程

`POST /v3/cards` / `memory.talk card create` 的服务端流程:rounds 展开、source_cards 校验、embedding、跨对象事件链。

相关:
- API 字段表: [`../../api/v3/cards.md`](../../api/v3/cards.md)
- CLI: [`../../cli/v3/card.md`](../../cli/v3/card.md)
- Card schema: [`../../structure/v3/talk-card.md`](../../structure/v3/talk-card.md)

## 总体顺序

```
1. 校验 insight 非空
2. 校验 card_id 前缀(如显式传入)+ 冲突检查
3. 校验 tags(同 PATCH 约束;一项违反整次拒绝)
4. 展开 rounds —— 必须 BEFORE source_cards 校验完成才能算"已就绪"
5. 校验 source_cards 引用都已存在
6. 算 insight 的 embedding
7. 写 SQLite cards + card_stats(原子)
8. 写 card_source_cards 行
9. 写 cards/<bucket>/<card_id>/card.json(immutable payload)
10. 写 events.jsonl(created 事件)
11. 写 LanceDB cards 表(text 段 + 向量)
12. 跨对象事件:
    - 每条被引用 session 的 events.jsonl 追加 card_extracted
    - 每条 source_cards[i].card_id 的 events.jsonl 追加 card_linked
```

任一前置校验失败 → 整体不落库。embedding 调失败 → 500,前面写过的也回滚(单事务边界覆盖 SQLite 写,文件层若已落则成 orphan,由 rebuild 路径清)。

## `rounds` 展开规则

入参的 `[{session_id, indexes}]` 在服务端展开成 `[{role, text, thinking?, session_id, index}]` 存入 card。`indexes` 语法:

| 形式 | 示例 | 含义 |
|---|---|---|
| 区间 | `"11-15"` | 闭区间 `[11, 15]`,展开为 `11..15` |
| 列表 | `"3,7,12"` | 离散 index 列表 |

约束(不满足整次拒绝):

- **严格单调递增** —— `"15-11"` / `"12,7,3"` 返 400 `indexes must be monotonically increasing`
- **越界 / session 不存在** —— 400 `index N out of range for session <sid>`
- 同 `session_id` 允许在 `rounds` 列表里多次出现(跳过中间段)
- 不同 item 之间无顺序约束

展开后每条 round 存为 `{role, text, thinking?, session_id, index}`。`session_id` / `index` 不进向量索引。

## `source_cards` 校验

每项 `{card_id, relation}`:

- `card_id` 必须 startswith `card_` 且**已经存在**
- `relation` 必须是 `derives_from` 或 `supersedes`
- 同一 `card_id` 允许以不同 `relation` 多次出现(罕见但不禁止)

### 为什么"创建时已存在"是 lineage DAG 的关键

Card 创建后不可改 + `source_cards` 只能引用**创建时已存在**的 card → **物理时序保证 lineage 图是有向无环图**。

后端**不做环检测**:不可能有环,因为引用是"过去 → 未来"单向的,过去的 card 在被引用时还无从知道未来要创建的 card。

后续可能扩展 `cites` / `merges` 等 relation;后端遇未识别 `relation` 返回 400。

## 事件链

| 事件类型 | 写到哪 | 触发 |
|---|---|---|
| `created` | `cards/<...>/events.jsonl` | 每次 card 创建 |
| `card_extracted` | 每条被引用 session 的 `sessions/<...>/events.jsonl` | 每条 rounds[i].session_id 各一条 |
| `card_linked` | 每条被引用 card 的 `cards/<...>/events.jsonl` | 每条 source_cards[i].card_id 各一条 |

这是**反向通知**模式:card 创建时主动给被引用对象发"我引用了你"事件。这样其他 card 的视角里看自己 events.jsonl 就能看到"谁在引我"。

`card_linked` 事件结构示例:

```json
{"event": "card_linked", "from_card": "card_01jz8k2m", "relation": "derives_from", "ts": "2026-04-10T14:30:00Z"}
```

## Stats 初始化

card 创建时同时 INSERT `card_stats` 行,全部计数器置 0:

```sql
INSERT INTO card_stats (card_id, review_up, review_down, review_neutral,
                        review_count, read_count, updated_at)
VALUES (?, 0, 0, 0, 0, 0, ?)
```

注意 0.9.0 起 `recall_count` 已 drop 列(改派生),不再在这里 init。详见 [forum-dynamics.md § 0.9.0:recall_count 改为派生](forum-dynamics.md#090recall_count-改为派生)。

## 跟 v2 的差异

| | v2 | v3 |
|---|---|---|
| 字段名 | `summary` | `insight` |
| 额外字段 | `from_search_id`(审计回填) | 删 |
| 关联 | 自动生成 card→session 默认 link(`ttl=0`) | **不生成 link** —— card↔session 隐式在 `rounds[].session_id` 里 |
| `source_cards` | 无(用 `POST /v2/links` 单独追加) | 内置字段,创建时确定不可改 |
| 副作用 | 写 default link 行 | 写 source_cards 行 + 初始化 stats |

# Cards API

## POST /v3/cards

创建一张 Talk-Card。自动计算 `insight` embedding、写入向量库、校验 `source_cards` 引用、初始化 stats。

v3 的 card API **只有写**。读一律走 `POST /v3/read`(`card_id` 是合法 id,不需要中间转换)。

CLI 对应 [`card`](../../cli/v3/card.md) 命令。

### 请求体

```json
{
  "insight": "选定 LanceDB 做向量存储",
  "rounds": [
    {"session_id": "sess_abc123", "indexes": "11-15"},
    {"session_id": "sess_def456", "indexes": "3,7,12"}
  ],
  "source_cards": [
    {"card_id": "card_01jzaaaa", "relation": "supersedes"},
    {"card_id": "card_01jzbbbb", "relation": "derives_from"}
  ],
  "card_id": "card_01jz8k2m"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `insight` | 是 | 一句话认知洞见,也是 embedding 锚点 |
| `rounds` | 是 | 引用列表,每项 `{session_id, indexes}`;可为空数组(纯 source_cards 派生的高阶 card) |
| `source_cards` | 否 | card 间关联,每项 `{card_id, relation}`;空数组 / 不传等价 |
| `card_id` | 否 | 不提供则自动生成 `card_<ULID>`;传入必须是 `card_<...>` 形态 |

详细字段语义和约束见 [`../../structure/v3/talk-card.md`](../../structure/v3/talk-card.md)。

### `rounds` 展开规则

服务端按 `session.rounds[].index` 把 `{session_id, indexes}` 展开为 `{role, text, thinking?, session_id, index}` 存入 card。`indexes` 语法:

| 形式 | 示例 | 含义 |
|---|---|---|
| 区间 | `"11-15"` | 闭区间 `[11, 15]`,展开为 `11..15` |
| 列表 | `"3,7,12"` | 离散 index 列表 |

约束(不满足整次拒绝):

- **严格单调递增** —— `"15-11"` / `"12,7,3"` 返 400 `indexes must be monotonically increasing`
- **越界 / session 不存在** —— 400 `index N out of range for session <sid>`
- 同 `session_id` 允许在 `rounds` 列表里多次出现(跳过中间段);不同 item 之间无顺序约束

### `source_cards` 校验

每项 `{card_id, relation}`:

- `card_id` 必须 startswith `card_` 且**已经存在**(append-only 保证 lineage 是 DAG;创建时还不存在的 card 没法引用)
- `relation` 必须是允许的值之一:`derives_from` / `supersedes`(未识别返 400)
- 同一 `card_id` 允许以不同 `relation` 多次出现(罕见但不禁止)

### 响应

```json
{"status": "ok", "card_id": "card_01jz8k2m"}
```

返回的 `card_id` 是带前缀裸 id,可直接喂给 `POST /v3/read` / `POST /v3/reviews`。

### 副作用

- 校验 `rounds`(展开 + 越界 + 单调) → 失败整条不落库
- 校验 `source_cards`(存在 + relation 白名单) → 失败整条不落库
- 展开后每条 round 存为 `{role, text, thinking?, session_id, index}`(`session_id` / `index` 不进向量索引)
- 自动计算 `insight` 的 embedding,写向量库
- **初始化 stats**:`review_up=0` / `review_down=0` / `review_neutral=0` / `review_count=0` / `read_count=0` / `recall_count=0`
- 落盘 `cards/{card_id[5:7]}/{card_id}/card.json`(immutable payload)+ `events.jsonl`(`created` 事件)
- 在每个被引用 session 的 `events.jsonl` 追加 `card_extracted` 事件(同 session 合并)
- 在每个 `source_cards[i].card_id` 的 `events.jsonl` 追加 `card_linked` 事件(被引视角)

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| `insight` 为空 / 非字符串 | 400, `insight required` |
| `rounds` 非数组 / 项格式错 | 400, `invalid rounds` |
| `rounds[].session_id` 不以 `sess_` 开头 | 400, `invalid session_id prefix` |
| `rounds[].session_id` 不存在 | 400, `session <sid> not found` |
| `indexes` 非单调递增 | 400, `indexes must be monotonically increasing` |
| `indexes` 越界 | 400, `index N out of range for session <sid>` |
| `source_cards[].card_id` 不以 `card_` 开头 | 400, `invalid source card_id prefix` |
| `source_cards[].card_id` 不存在 | 400, `source card <cid> not found` |
| `source_cards[].relation` 不识别 | 400, `unknown relation: <value>` |
| 显式传入 `card_id` 但前缀错 | 400, `invalid card_id prefix` |
| 显式传入 `card_id` 但已存在 | 409, `card_id already exists` |
| embedding provider 拒绝调用(API key 错 / 网络) | 500, `embedding failed: <details>` |

### 跟 v2 的差异

| | v2 | v3 |
|---|---|---|
| 字段名 | `summary` | `insight` |
| 额外字段 | `from_search_id` (审计回填) | 删 —— 没有 result_id / search_id 凭据机制 |
| 关联 | 自动生成 card→session 默认 link(`ttl=0`) | **不生成 link** —— card↔session 隐式在 `rounds[].session_id` 里 |
| `source_cards` | 无(用 `POST /v2/links` 单独追加) | 内置字段,创建时确定不可改 |
| 副作用 | 写 default link 行 | 写 source_cards 行 + 初始化 stats |

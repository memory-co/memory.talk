# Cards API

## POST /v3/cards

创建一张 Talk-Card。自动计算 `insight` embedding、写入向量库、校验 `source_cards` 引用、初始化 stats。

读单卡走 `POST /v3/read`(`card_id` 是合法 id)。0.8.x 新加了**列表 / 标签**两条维护端点:`GET /v3/cards`(按结构性过滤列 card)和 `PATCH /v3/cards/{cid}/tags`(改 user-side 标签)。

CLI 对应 [`card create | list | tag`](../../cli/v3/card.md) 三条子命令。

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
  "tags": {"project": "billing", "status": "draft"},
  "card_id": "card_01jz8k2m"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `insight` | 是 | 一句话认知洞见,也是 embedding 锚点 |
| `rounds` | 是 | 引用列表,每项 `{session_id, indexes}`;可为空数组(纯 source_cards 派生的高阶 card) |
| `source_cards` | 否 | card 间关联,每项 `{card_id, relation}`;空数组 / 不传等价 |
| `tags` | 否 | 创建时直接带 tag;约束跟 `PATCH /v3/cards/{cid}/tags` 完全一致(下方),任一违反整次拒绝 |
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

---

## GET /v3/cards

List card 元数据 + insight + stats(**不展开 rounds[]**)。CLI 入口 [`memory.talk card list`](../../cli/v3/card.md#card-list)。

### 查询参数

所有参数都可选,**默认列全部 card**(按 `created_at` 倒序,截 `limit`)。多参数 AND。

| 参数 | 类型 | 说明 |
|---|---|---|
| `tag` | string,重复可叠 | `K=V` 严格匹配 / `K` 只校验 key 存在。多个 `tag` AND。e.g. `?tag=project=billing&tag=status=draft` |
| `since` | ISO 8601 | `created_at >= since`。CLI 端的 `7d` / `12h` duration 在 CLI 层解析成 ISO 后再传 |
| `until` | ISO 8601 | `created_at <= until` |
| `limit` | int,默认 `20`,上限 `200` | 返回多少条 |

> **不接 stats 过滤**(`review_up`、`read_count` 等):走 `POST /v3/search` 的 DSL(`?where=read_count > 10 AND review_count = 0`),不在这边重复实现。
>
> **不接 lineage 过滤**(`cites_session`、`derives_from`、`supersedes`):后续 PR 加。

### 响应

```json
{
  "total": 47,
  "returned": 12,
  "cards": [
    {
      "card_id": "card_01jz8k2m",
      "insight": "选定 LanceDB 做向量存储,主要因为零依赖嵌入式架构",
      "created_at": "2026-05-24T09:12:03Z",
      "tags": {"project": "billing", "status": "draft"},
      "stats": {
        "review_up": 7,
        "review_down": 3,
        "review_neutral": 2,
        "review_count": 12,
        "read_count": 42,
        "recall_count": 18
      }
    }
  ]
}
```

- `total` 是匹配条件的总数(不受 `limit` 截断,服务端 `COUNT(*)` 取得);客户端用来提示"还有更多,加大 limit"。
- `returned == len(cards)`,等于 `min(total, limit)`。
- `stats` 语义见 [`../../structure/v3/talk-card.md#stats`](../../structure/v3/talk-card.md#stats)。
- `tags` 是 string→string 字典,空字典 `{}` 表示无 tag。

### 错误

| 情况 | 状态 |
|---|---|
| `limit` 超出 `[1, 200]` | 400 |
| `since` / `until` 不是合法 ISO 8601 | 400 |
| `since` / `until` 时间窗反向(since > until) | 400 |
| `tag` 串里出现非法 key | 400 |

---

## PATCH /v3/cards/{card_id}/tags

设 / 删 card 的 kv 标签。**PATCH 语义**(只动声明的 key,不传的 key 原样保留)。CLI 入口 [`memory.talk card tag`](../../cli/v3/card.md#card-tag)。

### append-only 不变性

card 的 immutable payload(`insight` / `rounds` / `source_cards`)依然**不可改** —— 这个端点只动 `tags` 列,跟 payload 完全解耦。详见 [`../../structure/v3/talk-card.md#user-side-metadata`](../../structure/v3/talk-card.md#user-side-metadata)。

### 请求体

```json
{
  "set":   {"project": "billing", "status": "verified"},
  "unset": ["draft", "obsolete"]
}
```

- `set`(可选,默认 `{}`):key→value 字典。已存在的 key 覆盖,不存在的 key 新增。
- `unset`(可选,默认 `[]`):要删除的 key 列表。key 不存在时**静默忽略**(不报错)。
- **两个都不传 / 都空 = 查询当前 tags 的语法糖**(同 `session tag <sid>` 不带参数 = 查询)。

### 约束(全部由服务端校验,跟 session tag 同款)

| 约束 | 报错 |
|---|---|
| key 必须匹配 `^[a-zA-Z][a-zA-Z0-9_.-]*$` | 400 `tag key '<k>' invalid` |
| value 长度 ≤ 200 char | 400 `tag value for '<k>' too long (max 200)` |
| 单 card tag 总数 ≤ 50(以 PATCH 后的最终量算) | 400 `too many tags (max 50)` |
| 同 key 同时出现在 `set` 和 `unset` | 400 `cannot both set and unset '<k>'` |
| card_id 不存在 | 404 |

任一违反 → **整次 PATCH 拒绝**,SQLite 不改。

### 响应

返回**改动后的全量 tags**(方便消费方拿到最终状态,不用回查):

```json
{
  "card_id": "card_01jz8k2m",
  "tags": {"project": "billing", "status": "verified"}
}
```

### 副作用

- 改写 SQLite `cards.tags`。
- 不改 `card.json`(immutable payload 落盘文件,append-only 不变)。
- 不动 stats / reviews / vector index / events.jsonl —— tag 不参与论坛动力学,不进 vector,也不算 lifecycle event。

# Reviews API

## POST /v3/reviews

对一张 card 写一条 review("回帖"):带 score(±1 / 0)+ comment + 来自某次 session 的证据 rounds。append-only,创建即冻结。

CLI 对应 [`review`](../../cli/v3/review.md) 命令。

### 请求体

```json
{
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "indexes": "20-25",
  "score": 1,
  "comment": "三个月后再次确认 LanceDB 选型有效——生产稳定运行,SQLite + LanceDB 混合栈跑顺"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `card_id` | 是 | 被 review 的 card,必须是 `card_<...>` |
| `session_id` | 是 | 本次 review 所在 session,必须是 `sess_<...>`。**单 session**(对比 card 的 rounds 可跨多 session) |
| `indexes` | 是 | 证据 round 范围,语法跟 `POST /v3/cards` 的 `rounds.indexes` 一致(`"20-25"` / `"3,7,12"`) |
| `score` | 是 | `1` 支持 / `0` 中立 / `-1` 反对。其它值报错 |
| `comment` | 否 | 一句话归因;`score=0` 时强烈建议填,服务端不强制 |
| `review_id` | 否 | 不提供则自动生成 `review_<ULID>`;传入必须是 `review_<...>` 形态 |

完整字段语义见 [`../../structure/v3/review.md`](../../structure/v3/review.md)。

### `(card_id, session_id)` 唯一性

**不去重**。同一对 `(card_id, session_id)` 允许多条 review —— 一次会话里在不同位置可能对同一张 card 表态多次(早期反对、深入后转支持),每条由 `indexes` 区分。

### 响应

```json
{
  "status": "ok",
  "review_id": "review_01jzr5kq",
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "score": 1
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | `"ok"` |
| `review_id` | string | 自动 / 透传的 review_id |
| `card_id` / `session_id` / `score` | 回显输入 | 方便调用方对账,不需重新解析 |

### 副作用

- 校验:`card_id` 存在 + `session_id` 存在 + `indexes` 不越界 + `score ∈ {-1, 0, 1}` → 任一失败整条不落库
- **累加被 review 的 card 的 stats**(原子 upsert):
  - `score = 1` → `review_up += 1`, `review_count += 1`
  - `score = -1` → `review_down += 1`, `review_count += 1`
  - `score = 0` → `review_neutral += 1`, `review_count += 1`
- 落盘 review 到 SQLite `reviews` 表 + 镜像到 `cards/{...}/{card_id}/reviews.jsonl`(append-only)
- 在 `cards/{...}/{card_id}/events.jsonl` 追加 `reviewed` 事件(detail 含 `review_id` / `score` / `session_id` / `indexes`;**不存 comment** —— 原文已在 reviews.jsonl 里)
- review 自身**不进向量索引** —— comment 是辅助说明,检索 card 时按 card 的 insight 匹配,review 跟着一起在 read 响应里呈现

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| `card_id` / `session_id` / `indexes` / `score` 缺失 | 400, `<field> required` |
| `card_id` 前缀错 | 400, `invalid card_id prefix` |
| `session_id` 前缀错 | 400, `invalid session_id prefix` |
| `card_id` 不存在 | 400, `card <cid> not found` |
| `session_id` 不存在 | 400, `session <sid> not found` |
| `indexes` 越界 | 400, `index N out of range for session <sid>` |
| `score` 非 -1/0/1 | 400, `score must be one of 1, 0, -1 (got <v>)` |
| `comment` 不是字符串 | 400, `comment must be string` |
| 显式传入 `review_id` 但前缀错 | 400, `invalid review_id prefix` |
| 显式传入 `review_id` 但已存在 | 409, `review_id already exists` |

### 读取

review **没有独立读取入口** —— 不存在 `GET /v3/reviews/{id}`。想看 review 走 `POST /v3/read {id: "card_xxx"}`,响应里 `card.reviews` 字段是按 `created_at` 倒序的全部 review。

理由:review 没有"作为独立对象被检索"的需求。它依附于 card,你想知道某张 card 怎么被看待就 read 这张 card,reviews 一并返回。

### 设计取舍

- **为什么不允许传入"撤销 review"**:review 是 append-only。表态错了的纠正方式是**再写一条相反 score 的 review**(comment 说明原因)。这跟"沉浮由动力学算"是配套的 —— 删旧不如让旧 review 也算进历史,后续 review 自然把它压下去。
- **为什么 `score=0` 还要单独存**:中立 review 是论坛动力学里"被讨论广度"的信号(对应设计 §5 "真讨论"的一种但不动方向)。把它跟 +1/-1 分开存,公式默认权重为 0,但保留了未来用它的可能。

# Reviews API

## POST /v4/positions/{position_id}/reviews

对一个 **Position（答案候选）** 写一条 review（"表态"）：带 `argument`（+1 顶 / 0 中立 / −1 踩）+ comment + 来自某次 session 的证据 rounds。append-only，创建即冻结。

沿用 v3 的 review 机制，只把 **target 从 `card_id` 换成 `position_id`** —— v4 一张卡有多个答案，表态针对的是"哪个答案"而非"整张卡"。`argument≠0` 的 review 就是一条 IBIS Argument（pro/con）；`argument=0` 是中立观察。

CLI 对应 [`review`](../../cli/v4/review.md) 命令。字段语义详见 [`../../structure/v4/review.md`](../../structure/v4/review.md)。

### 请求体

```json
{
  "session_id": "sess_def456",
  "indexes": "20-25",
  "argument": 1,
  "comment": "这轮对话里用户又一次明确要先给结论,印证简洁风格"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `session_id` | 是 | 本次表态所在 session，必须是 `sess_<...>`。**单 session**（对比 Position 出处可跨多 session） |
| `indexes` | 是 | 证据 round 范围，语法 `"20-25"` 区间 / `"3,7,12"` 离散列表；严格单调递增；越界报错 |
| `argument` | 是 | `1` 支持（顶 / pro）/ `0` 中立 / `−1` 反对（踩 / con）。其它值报错 |
| `comment` | 否 | 一句话归因；`argument=0` 时强烈建议填，服务端不强制 |
| `review_id` | 否 | 不提供则自动生成 `review_<ULID>`；传入必须是 `review_<...>` 形态 |

> `position_id` 在路径里，不在 body。`card_id` 服务端自动从 Position 反查并冗余进 review 行（答案不换卡 → 永不漂移，省"这张卡所有 review"的 join）。

### `(position_id, session_id)` 唯一性

**不去重**。同一对允许多条 review —— 一次会话里可能在不同位置对同一答案表态多次（早期反对、深入后转支持），每条由 `indexes` 区分。

### 响应

```json
{
  "status": "ok",
  "review_id": "review_01jzr5kq",
  "position_id": "pos_01jzp3nq",
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "argument": 1
}
```

`card_id` 是服务端反查回显（方便对账）。

### 副作用

- 校验：`position_id` 存在 + `session_id` 存在 + `indexes` 不越界 + `argument ∈ {-1, 0, 1}` → 任一失败整条不落库。
- **累加被表态 Position 的计数**（原子 upsert）：
  - `argument = 1` → `up_count += 1`
  - `argument = -1` → `down_count += 1`
  - `argument = 0` → `neutral_count += 1`
- **不动 `credence`** —— credence 不是存储字段，下次读 / 排序时按 `up−down`（或 Wilson）现算。`argument=0` / 中立不进 `up`/`down`，因此不影响 credence（只算 engagement、可能攒着衍生新 Position，见设计 §3）。
- 落盘 review 到 SQLite `reviews` 表（沿用 v3 review 的 canonical 存法）。
- review 自身**不进向量索引** —— comment 是辅助说明，检索按卡的 `issue` 匹配。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| `session_id` / `indexes` / `argument` 缺失 | 400, `<field> required` |
| `position_id` 前缀错（路径） | 400, `invalid position_id prefix` |
| `session_id` 前缀错 | 400, `invalid session_id prefix` |
| `position_id` 不存在 | 404, `position <pid> not found` |
| `session_id` 不存在 | 400, `session <sid> not found` |
| `indexes` 非单调 / 越界 | 400, `indexes must be monotonically increasing` / `index N out of range for session <sid>` |
| `argument` 非 -1/0/1 | 400, `argument must be one of 1, 0, -1 (got <v>)` |
| 显式 `review_id` 前缀错 / 已存在 | 400 / 409 |

### 读取

review **没有独立读取入口** —— 不存在 `GET /v4/.../reviews/{id}`。想看某 Position 的表态走 `POST /v3/read {id: "pos_xxx"}`（沿用 v3 read，按前缀判型），响应里带这个 Position 的 reviews（按 `created_at` 倒序）。

### 不变性

- **没有"撤销 review"**：review append-only。表态错了就**再写一条相反 `argument` 的 review**(comment 说明原因)。
- **`argument=0`(中立)单独计数**:不动 credence(不进 `up`/`down`);中立堆积可离线衍生出新 Position(机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §3 末)。

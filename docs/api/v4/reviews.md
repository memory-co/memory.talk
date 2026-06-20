# Reviews API

review 的 **target 有两种**，对应两个平行端点（都沿用 v3 review 机制，只是 target 不同）：

| target_kind | 端点 | target 寻址 |
|---|---|---|
| `position` | `POST /v4/cards/{card_id}/positions/{position}/reviews` | `card_id#p<n>` |
| `link` | `POST /v4/cards/{card_id}/links/{link}/reviews`（见 [card-links.md](card-links.md)） | `card_id#l<n>` |

两者请求体 / 响应 / 错误 / 唯一性**完全同构**，区别只在路径段（`{position}` = `p<n>` vs `{link}` = `l<n>`）和派生的 `target_kind`。下面以 positions 版为准详述；links 版见 [card-links.md](card-links.md#post-v4cardscard_idlinkslinkreviews)。

## POST /v4/cards/{card_id}/positions/{position}/reviews

对一个 **Position（答案候选）** 写一条 review（"表态"）：带 `argument`（+1 顶 / 0 中立 / −1 踩）+ comment + 来自某次 session 的证据 rounds。append-only，创建即冻结。

沿用 v3 的 review 机制，只把 **target 从整张卡下放到某个答案** —— v4 一张卡有多个答案，表态针对的是"哪个答案"而非"整张卡"。Position **没有独立 id**，是它所属卡的附属，寻址 `<card_id>#p<n>`（路径里拆成 `{card_id}` + `{position}`，`{position}` = 卡内序号 `p1`/`p2`…，正如 mark 是 `<session_id>#m<n>`）。`argument≠0` 的 review 就是一条 IBIS Argument（pro/con）；`argument=0` 是中立观察。

CLI 对应 [`card review --target card_xxx#p<n>`](../../cli/v4/card.md#card-review)（同一 `--target` flag 也收 `card_xxx#l<n>` 去打 Link）。字段语义详见 [`../../structure/v4/review.md`](../../structure/v4/review.md)。

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

> `card_id` + `position`（`p<n>`）都在路径里，不在 body。review 行冗余存这两列（答案不换卡 → 永不漂移，省"这张卡所有 review"的 join）。

### `(card_id, position, session_id)` 唯一性

**不去重**。同一对允许多条 review —— 一次会话里可能在不同位置对同一答案表态多次（早期反对、深入后转支持），每条由 `indexes` 区分。

### 响应

```json
{
  "status": "ok",
  "review_id": "review_01jzr5kq",
  "card_id": "card_01jz8k2m",
  "target": "p1",
  "target_kind": "position",
  "session_id": "sess_def456",
  "argument": 1
}
```

`card_id` + `target` 是路径回显（方便对账，寻址 `card_01jz8k2m#p1`）。`target_kind` 从路径段（positions / links）派生（这里 = `position`；links 端点 = `link`）。

### 副作用

- 校验：`card_id` 存在 + 卡内有 `position`（`p<n>`）+ `session_id` 存在 + `indexes` 不越界 + `argument ∈ {-1, 0, 1}` → 任一失败整条不落库。
- **累加被表态 Position 的计数**（原子 upsert）：
  - `argument = 1` → `up_count += 1`
  - `argument = -1` → `down_count += 1`
  - `argument = 0` → `neutral_count += 1`
- **不动 `credence`** —— credence 不是存储字段，下次读 / 排序时按 `up−down`（或 Wilson）现算。`argument=0` / 中立不进 `up`/`down`，因此不影响 credence（只算 engagement、可能攒着衍生新 Position，见设计 §3）。
- 落盘 review 到 SQLite `reviews` 表（`target=p<n>`、`target_kind=position`；沿用 v3 review 的 canonical 存法）。
- review 自身**不进向量索引** —— comment 是辅助说明，检索按卡的 `issue` 匹配。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| `session_id` / `indexes` / `argument` 缺失 | 400, `<field> required` |
| `card_id` 前缀错（路径） | 400, `invalid card_id prefix` |
| `position` 不是 `p<n>` 形态（路径） | 400, `invalid position` |
| `session_id` 前缀错 | 400, `invalid session_id prefix` |
| `card_id` 不存在 | 404, `card <cid> not found` |
| `position` 在卡内不存在 | 404, `position <card_id>#<p> not found` |
| `session_id` 不存在 | 400, `session <sid> not found` |
| `indexes` 非单调 / 越界 | 400, `indexes must be monotonically increasing` / `index N out of range for session <sid>` |
| `argument` 非 -1/0/1 | 400, `argument must be one of 1, 0, -1 (got <v>)` |
| 显式 `review_id` 前缀错 / 已存在 | 400 / 409 |

### 读取

review **没有独立读取入口** —— 不存在 `GET /v4/.../reviews/{id}`。想看某 Position / Link 的表态走 [`POST /v4/read`](read.md) `{id: "card_xxx#p1"}` 或 `{id: "card_xxx#l1"}`（按 `#p`/`#l` 分片判型），响应里带这个 Position / Link 的 reviews（按 `created_at` 倒序）。

### 不变性

- **没有"撤销 review"**：review append-only。表态错了就**再写一条相反 `argument` 的 review**(comment 说明原因)。
- **`argument=0`(中立)单独计数**:不动 credence(不进 `up`/`down`);中立堆积可离线衍生出新 Position(机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §3 末)。

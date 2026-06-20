# Cards API

卡 = 一个**问题**（`issue`）+ 它底下的若干**答案候选**（Position）。本页端点：列卡、给卡加答案、列答案、列出处（card→session）。**卡的创建不在本页** —— 卡由 mark 写路径建（[`session-marks.md`](session-marks.md) 的 `#…？` miss）。

读单卡 / 单 Position 走 [`POST /v4/read`](read.md)（`card_` 与 `card_…#p<n>` 分片都认）。对答案表态走 [`POST /v4/cards/{cid}/positions/{p}/reviews`](reviews.md)。

CLI 对应 [`card position`](../../cli/v4/card.md)(问题由 [`session mark`](../../cli/v4/session.md#session-mark) 的 `#…？` 建)（读卡走 [`read`](../../cli/v4/read.md))。字段语义详见 [`../../structure/v4/card.md`](../../structure/v4/card.md)。

---

## GET /v4/cards

列卡元数据（`issue` + 每卡 Position 数 + 创建时间），**不展开 Position**。CLI:列卡走 [`search ''`](../../cli/v4/search.md)（空 query 按时间列）;看单卡的全部答案走 [`read <card_id>`](../../cli/v4/read.md)。

### 查询参数

所有可选，默认按 `created_at` 倒序、截 `limit`。

| 参数 | 类型 | 说明 |
|---|---|---|
| `since` | ISO 8601 | `created_at >= since`（CLI 端 `7d` / `12h` 在 CLI 层解析成 ISO 再传） |
| `until` | ISO 8601 | `created_at <= until` |
| `limit` | int，默认 `20`，上限 `200` | 返回多少条 |

### 响应

```json
{
  "total": 47,
  "returned": 2,
  "cards": [
    {"card_id": "card_01jz8k2m", "issue": "用户偏好什么回答风格?", "position_count": 3, "link_count": 2, "created_at": "2026-05-24T09:12:03Z"},
    {"card_id": "card_01jzp3nq", "issue": "缓存层选 Redis 还是本地?", "position_count": 0, "link_count": 0, "created_at": "2026-05-25T14:21:00Z"}
  ]
}
```

- `total` 是匹配总数（`COUNT(*)`，不受 `limit` 截断）；`returned == len(cards) == min(total, limit)`。
- `position_count = 0` = 一张还在等答案的卡。

### 错误

| 情况 | 状态 |
|---|---|
| `limit` 超出 `[1, 200]` | 400 |
| `since` / `until` 非 ISO 8601，或时间窗反向 | 400 |

---

## POST /v4/cards/{card_id}/positions

给一张已存在的卡**新增一个答案候选**（Position）。这就是"答案竞争"的入口——同一个问题下不同答案各自被顶踩、按现算 credence 竞争。

### 请求体

```json
{
  "claim": "偏详细,默认带背景和权衡",
  "scope": "新人 onboarding 场景",
  "source": {"session_id": "sess_def456", "indexes": "3,7,12"},
  "forked_from": "p1"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `claim` | 是 | 答案文本（内联） |
| `scope` | 否 | 一句话适用场景软提示，默认 `""` |
| `source` | 否 | **答案的**出处 `{session_id, indexes}` → 落一条 `position_sessions`（position→session，经 `indexes`；`mark` 可选） |
| `forked_from` | 否 | 信念分叉血缘：本答案从**本卡的哪个旧 Position** 分出来（同卡内的 `p<n>`，如 `"p1"`，保认知史；见 [`../../structure/v4/card.md`](../../structure/v4/card.md)） |

### 响应

```json
{"status": "ok", "card_id": "card_01jz8k2m", "position": "p2"}
```

> `position` = 卡内自动递增的序号（`p1` / `p2`…），不由客户端指定；全址 = `card_01jz8k2m#p2`，正如 mark 是 `<session_id>#m<n>`。

### 副作用

- 校验 `card_id` 存在、`claim` 非空、`forked_from`（如给）是**本卡内**已存在的 `p<n>` → 任一失败整条不落库。
- 落一个 Position（计数全 0），canonical 写 `positions/p<n>.json`（文件名 = 卡内序号）。
- 若带 `source`：落一条 `position_sessions`（position→session，经 `indexes`）。**不写 `card_sessions`**——那是 card→session（经 mark）的另一条链路。
- **不动其它 Position**：append-only，新增不覆盖；"哪个答案当下用"由召回时现算 credence 决定，不在这里改任何状态位。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| `card_id` 不存在 | 404, `card <cid> not found` |
| `claim` 为空 | 400, `claim required` |
| `source.session_id` 前缀错 / 不存在 / `indexes` 越界 | 400, `invalid session_id prefix` / `session <sid> not found` / `index N out of range for session <sid>` |
| `forked_from` 不是 `p<n>` 形态 / 本卡内不存在 | 400, `invalid forked_from` / 404, `position <card_id>#<p> not found` |

---

## GET /v4/cards/{card_id}/positions

列一张卡底下的所有答案候选，各带 **up/down/neutral 计数 + 服务端现算的 credence**，默认按现算 credence 降序（平手用最近一条 review 时间）。

### 响应

```json
{
  "card_id": "card_01jz8k2m",
  "issue": "用户偏好什么回答风格?",
  "positions": [
    {
      "position": "p1",
      "claim": "偏简洁,先给结论再展开",
      "up_count": 7, "down_count": 1, "neutral_count": 2, "review_count": 10,
      "credence": 6,
      "scope": "技术问答场景;闲聊不一定适用",
      "forked_from": null,
      "last_reviewed_at": "2026-05-30T10:00:00Z",
      "created_at": "2026-05-24T09:12:03Z"
    },
    {
      "position": "p2",
      "claim": "偏详细,默认带背景和权衡",
      "up_count": 2, "down_count": 0, "neutral_count": 1, "review_count": 3,
      "credence": 2,
      "scope": "新人 onboarding 场景",
      "forked_from": "p1",
      "last_reviewed_at": "2026-05-28T18:30:00Z",
      "created_at": "2026-05-26T11:00:00Z"
    }
  ]
}
```

- `up_count` / `down_count` / `neutral_count` = 这个 Position 收到 `argument=+1`/`−1`/`0` 的 review 数（**存储字段**）。
- `credence` = 服务端按 `f(up, down)` **现算**的校验分（示例用 `up−down`；实际公式 `up−down` 还是 Wilson 下界留给 search-ranking 的 v4 版定）。**不是存储字段**，每次现算。
- `last_reviewed_at` = 最近一条 review 的时间，排序平手时的 tiebreak 依据；无 review 时回退 `created_at`。
- 列表里 credence 最高的那个就是"当下用的答案"——**没有 `accepted` 字段**，是排序结果。
- `scope` 是软提示文本，召回注入时一起喂给 LLM；这个端点只是回显，**不做任何门禁**。

### 错误

| 情况 | 状态 |
|---|---|
| `card_id` 不存在 | 404 |

---

## GET /v4/cards/{card_id}/sessions

列这张卡的**出处**:哪些 session 的哪条 mark 建 / 连了它(card→session,经 **mark**)。

> card→session **没有显式写端点** —— 只由 mark 写路径自动写([`POST /v4/sessions/{id}/marks`](session-marks.md) 里 `#…？` miss 建新卡 / hit 连老卡时各记一条 `card_sessions`)。本端点只读。反查「某 session 建/连了哪些卡」走 [`GET /v4/sessions/{session_id}/cards`](sessions.md#get-v4sessionssession_idcards)。答案级出处(position→session)是另一条链路,见 [`POST positions` 的 `source`](#post-v4cardscard_idpositions) → [`position-session.md`](../../structure/v4/position-session.md)。数据结构见 [`../../structure/v4/card-session.md`](../../structure/v4/card-session.md)。

### 响应

```json
{
  "card_id": "card_01jz8k2m",
  "sessions": [
    {"session_id": "sess_abc", "mark": "m1", "created_at": "2026-05-24T09:12:03Z"},
    {"session_id": "sess_def", "mark": "m3", "created_at": "2026-05-24T09:40:00Z"}
  ]
}
```

每行 = 某 session 的某条 mark(`m<n>`,寻址 `session_id#mark`)建 / 连了本卡;同一对可多条(不同 mark)。

### 错误

| 情况 | 状态 |
|---|---|
| 路径 `card_id` 不存在 | 404 |
| `card_id` 前缀 / 格式不合法 | 400 |

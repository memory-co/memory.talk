# Read API

## POST /v4/read

按 id 读一个对象。前缀判型:`card_` → 卡(问题 + 它所有答案)、`pos_` → 单个答案(+ 它收到的 review)、`sess_` → session(沿用 v3 session 形态)。

CLI 对应 [`read <id>`](../../cli/v4/read.md)。字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md)。

### 请求体

```json
{"id": "card_01jz8k2m"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | `card_<…>` / `pos_<…>` / `sess_<…>`,前缀决定读什么 |

### 响应 — `card_`(问题 + 所有答案)

跟 [`GET /v4/cards/{card_id}/positions`](cards.md) 同形,外加 `links` / `sessions`:

```json
{
  "card_id": "card_01jz8k2m",
  "issue": "用户偏好什么回答风格?",
  "created_at": "2026-06-18T14:30:00Z",
  "position_count": 1, "link_count": 1,
  "positions": [
    {
      "position_id": "pos_01jzp3nq",
      "claim": "默认简洁、要点优先",
      "up_count": 7, "down_count": 1, "neutral_count": 0, "review_count": 8,
      "credence": 6,
      "scope": "日常问答;调试场景另说",
      "forked_from_position_id": null,
      "last_reviewed_at": "2026-05-30T10:00:00Z",
      "created_at": "2026-06-18T14:30:00Z"
    }
  ],
  "links": [{"type": "specializes", "target_id": "card_01jzsub", "dir": "in"}],
  "sessions": [{"session_id": "sess_abc", "position_id": "pos_01jzp3nq", "indexes": "11-15"}]
}
```

- `positions` 按现算 `credence` 降序(平手用 `last_reviewed_at`)。`credence` 是服务端**现算**派生值,不在存储里。
- `links` = 这张卡的 IBIS 边(`card_links`),`dir` = `out`(本卡指出去)/ `in`(别的卡指过来)。
- `sessions` = 出处(`card_sessions`)。
- 一张**没有 Position** 的卡:`positions` 为 `[]`(还在等答案的问题,合法)。

### 响应 — `pos_`(单个答案 + 它的 review)

```json
{
  "position_id": "pos_01jzp3nq",
  "card_id": "card_01jz8k2m",
  "claim": "默认简洁、要点优先",
  "up_count": 7, "down_count": 1, "neutral_count": 0, "review_count": 8,
  "credence": 6,
  "scope": "日常问答;调试场景另说",
  "forked_from_position_id": null,
  "created_at": "2026-06-18T14:30:00Z",
  "reviews": [
    {"review_id": "review_01jzr5kq", "session_id": "sess_def", "indexes": "20-25", "argument": 1, "comment": "...", "created_at": "2026-05-30T10:00:00Z"}
  ]
}
```

- `reviews` = 这个 Position 收到的全部 review,按 `created_at` 倒序。review 无独立读取入口,只在这里(或 card 读)带出。

### 响应 — `sess_`

沿用 v3 session 读取形态(`meta` + `rounds`),见 [`../v3/`](../v3/) / v3 session 文档。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| `id` 缺失 / 前缀不识别 | 400, `invalid id prefix` |
| `id` 合法但不存在 | 404, `not found` |

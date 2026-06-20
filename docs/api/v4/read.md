# Read API

## POST /v4/read

按 id 判型读一个对象:`card_` → 卡(问题 + 它所有答案 + 边)、`card_…#p<n>` 分片 → 单个答案(+ 它收到的 review)、`card_…#l<n>` 分片 → 单条 CardLink(+ 它收到的 review)、`sess_` → session(沿用 v3 session 形态)。Position / CardLink 都没有独立 id,寻址 `<card_id>#p<n>` / `<card_id>#l<n>`(正如 mark 是 `<session_id>#m<n>`),`read` 见到 `#p` 分片定位「这张卡的第 n 个答案」、`#l` 分片定位「第 n 条边」。

CLI 对应 [`read <id>`](../../cli/v4/read.md)。字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md)。

### 请求体

```json
{"id": "card_01jz8k2m"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | `card_<…>` / `card_<…>#p<n>`(某卡的某答案)/ `card_<…>#l<n>`(某卡的某条边)/ `sess_<…>`,判型决定读什么 |

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
      "position": "p1",
      "claim": "默认简洁、要点优先",
      "up_count": 7, "down_count": 1, "neutral_count": 0, "review_count": 8,
      "credence": 6,
      "scope": "日常问答;调试场景另说",
      "forked_from": null,
      "last_reviewed_at": "2026-05-30T10:00:00Z",
      "created_at": "2026-06-18T14:30:00Z"
    }
  ],
  "links": [{"link": "l1", "type": "specializes", "target_id": "card_01jzsub", "target_type": "card", "dir": "out", "claim": "本卡是它的特例,同一套 auth", "up_count": 4, "down_count": 0, "neutral_count": 1, "review_count": 5, "credence": 4}],
  "sessions": [{"session_id": "sess_abc", "mark": "m1"}]
}
```

- `positions` 按现算 `credence` 降序(平手用 `last_reviewed_at`)。`credence` 是服务端**现算**派生值,不在存储里。
- `links` = 这张卡的 IBIS 边(`card_links`,受治理),各带 `link`(`l<n>`)+ `claim` + 顶踩计数 + 现算 `credence`;`dir` = `out`(本卡指出去,寻址 `card_…#l<n>`)/ `in`(别的卡指过来)。**低于 credence 阈值的边淡出 / 隐藏**(存在即合理,边不竞争);`credence` 同样不在存储里。
- `sessions` = card→session 出处(`card_sessions`,经 **mark**;哪条 mark 建/连了这张卡)。答案级出处(某 Position 来自哪几轮 `indexes`)是另一条链路 `position_sessions`,不在这里。
- 一张**没有 Position** 的卡:`positions` 为 `[]`(还在等答案的问题,合法)。

### 响应 — `card_…#p<n>`(单个答案 + 它的 review)

```json
{
  "card_id": "card_01jz8k2m",
  "position": "p1",
  "claim": "默认简洁、要点优先",
  "up_count": 7, "down_count": 1, "neutral_count": 0, "review_count": 8,
  "credence": 6,
  "scope": "日常问答;调试场景另说",
  "forked_from": null,
  "created_at": "2026-06-18T14:30:00Z",
  "reviews": [
    {"review_id": "review_01jzr5kq", "session_id": "sess_def", "indexes": "20-25", "argument": 1, "comment": "...", "created_at": "2026-05-30T10:00:00Z"}
  ]
}
```

- `reviews` = 这个 Position 收到的全部 review,按 `created_at` 倒序。review 无独立读取入口,只在这里(或 card 读)带出。

### 响应 — `card_…#l<n>`(单条 CardLink + 它的 review)

跟 `card_…#p<n>` 同构,读的是一条受治理边:

```json
{
  "card_id": "card_01jz8k2m",
  "link": "l1",
  "type": "specializes",
  "target_id": "card_01jzyyyy",
  "target_type": "card",
  "claim": "本卡是它的一个特例 —— 都走同一套 auth,只是把范围收窄到 OAuth 回调这一段。",
  "up_count": 4, "down_count": 0, "neutral_count": 1, "review_count": 5,
  "credence": 4,
  "created_at": "2026-06-18T15:00:00Z",
  "reviews": [
    {"review_id": "review_01jzr5kq", "session_id": "sess_def", "indexes": "30-34", "argument": 1, "comment": "...", "created_at": "2026-06-18T15:00:00Z"}
  ]
}
```

- `reviews` = 这条边收到的全部 review,按 `created_at` 倒序。`credence` 现算、不在存储里。字段语义见 [`../../structure/v4/card-link.md`](../../structure/v4/card-link.md)。

### 响应 — `sess_`

session 读取 = 头部元数据 + 展开的 `rounds`,完全只读(不更新任何计数;session 不参与卡的动力学)。rounds 一次性全返回,不支持窗口参数。

```json
{
  "type": "session",
  "read_at": "2026-04-20T14:32:05Z",
  "session": {
    "session_id": "sess_187c6576",
    "source": "claude-code",
    "created_at": "2026-04-10T14:30:00Z",
    "metadata": {"project": "/home/user/myapp"},
    "rounds": [
      {
        "index": 1,
        "round_id": "r001",
        "speaker": "user",
        "role": "human",
        "content": [{"type": "text", "text": "ChromaDB vs LanceDB?"}]
      },
      {
        "index": 2,
        "round_id": "r002",
        "speaker": "assistant",
        "role": "assistant",
        "content": [{"type": "text", "text": "推荐 LanceDB,零依赖嵌入式"}]
      }
    ]
  }
}
```

Round / ContentBlock 结构见 [`../../structure/v4/session.md`](../../structure/v4/session.md)。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| `id` 缺失 / 前缀不识别 | 400, `invalid id prefix` |
| `id` 合法但不存在 | 404, `not found` |

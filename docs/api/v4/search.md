# Search API

## POST /v4/search

有意识检索:拿 query 撞**问题(`issue`)**——`cards` 向量库 + FTS 混合召回,返回匹配的卡,每张带它**当下用的答案**(现算 credence 最高的 Position)。可选 `where` DSL 按计数 / 时间过滤。

跟 [`POST /v4/recall`](recall.md) 的区别:recall 是 hook 阶段无意识注入(极简);search 是 agent 主动检索(带 query + DSL + 排序)。

CLI 对应 [`search <query> [--where DSL]`](../../cli/v4/search.md)。

### 请求体

```json
{
  "query": "回答风格",
  "where": "up_count >= 3 AND down_count = 0",
  "limit": 20
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `query` | 是(可空串) | 撞 `issue` 的检索词。空串 = 不做相关性、纯靠 `where` 过滤 |
| `where` | 否 | DSL 过滤(见下),作用在卡的当下答案的计数 / 卡的元数据上 |
| `limit` | 否,默认 `20`,上限 `200` | 返回多少张卡 |

### 排序

- `query` 非空:按**检索相关性**(向量 + FTS)排序。**v4 没有 v3 那套沉浮公式**——相关性只在这一刻算,不掺存储的"热度"信号。
- `query` 空:按 `created_at` 倒序。
- 卡内的多个答案:取现算 `credence` 最高的那个作"当下答案"返回(平手用最近一条 review 时间)。

### `where` DSL 字段

作用在**卡的当下答案 + 卡元数据**上。可用字段:

| 字段 | 含义 |
|---|---|
| `up_count` / `down_count` / `neutral_count` | 当下答案的顶 / 踩 / 中立计数 |
| `credence` | 当下答案的现算校验分 |
| `position_count` | 这张卡有几个答案(`0` = 还在等答案的问题) |
| `created_at` | 卡创建时间(`since` / `until` 也可走查询参数) |

> **v3 的 `read_count` / `recall_count` / 沉浮公式在 v4 不存在**——v4 不回写"被读 / 被召回"信号(相关性召回时现算)。所以 v3 那条招牌 shadow-knowledge 查询(`read_count > 10 AND review_count = 0`)在 v4 改成「**被提出但没人验证的答案**」:`neutral_count > 3 AND up_count = 0 AND down_count = 0`,或「**还没答案的问题**」:`position_count = 0`。

### 响应

```json
{
  "query": "回答风格",
  "total": 3,
  "returned": 3,
  "cards": [
    {
      "card_id": "card_01jz8k2m",
      "issue": "用户偏好什么回答风格?",
      "position_count": 3,
      "top_position": {
        "position_id": "pos_01jzp3nq",
        "claim": "默认简洁、要点优先",
        "up_count": 7, "down_count": 1, "neutral_count": 0,
        "credence": 6,
        "scope": "日常问答;调试场景另说"
      },
      "score": 0.82,
      "created_at": "2026-06-18T14:30:00Z"
    }
  ]
}
```

- `top_position` = 当下答案(现算 credence 最高);`position_count = 0` 时为 `null`。
- `score` = 检索相关性(`query` 空时省略)。
- 要看一张卡的**全部**答案走 [`POST /v4/read`](read.md) `{id: card_…}`。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| `query` 缺失(非字符串) | 400, `query required` |
| `where` DSL 解析失败 / 用了未知字段 | 400, `<detail>` |
| `limit` 超出 `[1, 200]` | 400 |

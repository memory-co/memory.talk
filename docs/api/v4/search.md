# Search API

## POST /v4/search

有意识检索:**统一跨三种记忆**做语义召回,按相关性排成一条混合结果流,每条带 `kind` 标识自己属于哪一类:

- **`card`** —— v4 问题图谱。拿 query 撞**问题 + 答案**(`issue` + `claim`,`cards` + `positions` 向量库),命中卡带它**最相关 / 当下的答案**(claim 命中取该答案,否则取现算 credence 最高的 Position)。
- **`insight`** —— 迁移过来的 v3 老知识(`insights` 向量库)。
- **`session`** —— 原始会话轮次(`rounds` 向量库),命中是带上下文的轮次摘录。

为什么要统一:真实安装往往有大量 session + insight,但 v4 卡在 mark 写路径把图谱建起来之前**是 0**。只搜卡的 search 在第一天毫无用处;把 insight + session 一并纳入,search 从首次 ingest 起就有用(issue #7)。三类共用同一条排序轴 —— 检索原始相关性(searchbase `score`)。

跟 [`POST /v4/recall`](recall.md) 的区别:recall 是 hook 阶段无意识注入(极简,只回卡);search 是 agent 主动检索(带 query + DSL + 跨三库排序)。

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
| `query` | 是(可空串) | 撞 `issue` / `claim` / `insight` / `round` 的检索词。空串 = 不做相关性、只列卡(纯靠 `where` 过滤) |
| `where` | 否 | DSL 过滤(见下),**只作用在 `card` 结果**的当下答案计数 / 卡元数据上;`insight` / `session` 结果不受 DSL 过滤 |
| `limit` | 否,默认 `20`,上限 `200` | 整条混合流最多返回多少条 |

### 排序

- `query` 非空:三库各自召回后**合并按检索相关性**(searchbase `score`)排成一条流。**v4 没有 v3 那套沉浮公式**——相关性只在这一刻算,不掺存储的"热度"信号。
- `query` 空:**只列卡**,按 `created_at` 倒序(insight / session 无排序轴,空 query 不纳入)。
- 卡内的多个答案:取现算 `credence` 最高的那个作"当下答案"返回(平手用最近一条 review 时间)。

### `where` DSL 字段

**只过滤 `card` 结果**(作用在卡的当下答案 + 卡元数据上);`insight` / `session` 结果按相关性返回、不被 DSL 过滤。给了 `where` 且没有卡命中时,仍会返回 insight / session 命中。可用字段:

| 字段 | 含义 |
|---|---|
| `up_count` / `down_count` / `neutral_count` | 当下答案的顶 / 踩 / 中立计数 |
| `credence` | 当下答案的现算校验分 |
| `position_count` | 这张卡有几个答案(`0` = 还在等答案的问题) |
| `created_at` | 卡创建时间(`since` / `until` 也可走查询参数) |

> **v3 的 `read_count` / `recall_count` / 沉浮公式在 v4 不存在**——v4 不回写"被读 / 被召回"信号(相关性召回时现算)。所以 v3 那条招牌 shadow-knowledge 查询(`read_count > 10 AND review_count = 0`)在 v4 改成「**被提出但没人验证的答案**」:`neutral_count > 3 AND up_count = 0 AND down_count = 0`,或「**还没答案的问题**」:`position_count = 0`。

### 响应

`cards` 是一条**混合流**(键名沿用 `cards` 不变,但每条带 `kind`):

```json
{
  "query": "回答风格",
  "total": 3,
  "returned": 3,
  "cards": [
    {
      "kind": "card",
      "card_id": "card_01jz8k2m",
      "issue": "用户偏好什么回答风格?",
      "position_count": 3,
      "top_position": {
        "position": "p1",
        "claim": "默认简洁、要点优先",
        "up_count": 7, "down_count": 1, "neutral_count": 0,
        "credence": 6,
        "scope": "日常问答;调试场景另说"
      },
      "relevance": 0.82,
      "created_at": "2026-06-18T14:30:00Z"
    },
    {
      "kind": "insight",
      "insight_id": "insight_01jx...",
      "insight": "用户在调试场景偏好先给定位再给改法",
      "relevance": 0.61,
      "created_at": "2026-04-02T09:00:00Z"
    },
    {
      "kind": "session",
      "session_id": "sess-...",
      "source": "claude-code",
      "round_count": 42,
      "hit_count": 2,
      "hits": [
        {"index": 17, "role": "human", "text": "你回答时能不能先给结论？", "score": 0.55}
      ],
      "relevance": 0.55,
      "created_at": "2026-03-11T12:00:00Z"
    }
  ]
}
```

- 每条结果靠 `kind`(`card` / `insight` / `session`)区分形态。
- `card`:`top_position` = 当下答案(现算 credence 最高);`position_count = 0` 时为 `null`。
- `session`:`hits` 是命中轮次的摘录(单轮文本有上限截断);`hit_count` 是命中总数。
- `relevance` = 检索原始相关性,三类共用的排序轴(`query` 空时只列卡,无此字段)。
- 要看一张卡的**全部**答案走 [`POST /v4/read`](read.md) `{id: card_…}`;看整段 session 走 `{id: sess-…}`。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| `query` 缺失(非字符串) | 400, `query required` |
| `where` DSL 解析失败 / 用了未知字段 | 400, `<detail>` |
| `limit` 超出 `[1, 200]` | 400 |

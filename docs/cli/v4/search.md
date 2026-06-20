# search

有意识检索:**统一跨三种记忆**做语义召回,排成一条按相关性混合的流,每条带 `kind`:

- **`card`** —— v4 问题图谱(撞 `issue` + `claim`),命中卡带它**最相关 / 当下的答案**(claim 命中取该答案,否则取现算 credence 最高的)。
- **`insight`** —— 迁移过来的 v3 老知识。
- **`session`** —— 原始会话轮次,命中是带上下文的轮次摘录。

真实安装在 mark 写路径建起卡图谱前,v4 卡可能是 0;把 insight + session 一并纳入,search 从首次 ingest 起就有用(issue #7)。

```bash
memory.talk search <query> [--where '<DSL>'] [--limit N] [--json]
```

调 [`POST /v4/search`](../../api/v4/search.md)。跟 [`recall`](recall.md) 的区别:recall 是 hook 阶段无意识注入;search 是主动检索(带 query + DSL)。

## 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `<query>` | 是(可空串 `""`) | 撞 `issue` / `claim` / `insight` / `round` 的检索词;空串 = 只列卡、纯按 `--where` 过滤 |
| `--where` | 否 | DSL 过滤(见下),**只作用在 `card` 结果**上 |
| `--limit` | 否,默认 `20`,上限 `200` | 整条混合流最多返回多少条 |

## 排序

- `query` 非空:三库各自召回后**合并按检索相关性**排成一条流。**v4 无沉浮公式**——相关性只在这一刻算,不掺存储热度。
- `query` 空:**只列卡**,按 `created_at` 倒序(insight / session 不纳入空 query)。
- 卡内取现算 `credence` 最高的答案作"当下答案"(平手按最近 review 时间)。

## `--where` DSL

**只过滤 `card` 结果**(作用在卡的当下答案 + 卡元数据上);`insight` / `session` 命中按相关性返回、不被 DSL 过滤。给了 `--where` 且没有卡命中时,仍会返回 insight / session 命中。字段:

| 字段 | 含义 |
|---|---|
| `up_count` / `down_count` / `neutral_count` | 当下答案的顶 / 踩 / 中立计数 |
| `credence` | 当下答案的现算校验分 |
| `position_count` | 这张卡有几个答案(`0` = 还在等答案) |
| `created_at` | 卡创建时间 |

```bash
# 被验证得最稳的问答
memory.talk search "回答风格" -w 'up_count >= 5 AND down_count = 0'

# 还在等答案的问题(没人给过 Position)
memory.talk search "" -w 'position_count = 0'

# 被提出但没人验证的答案(v4 版 shadow knowledge)
memory.talk search "" -w 'neutral_count > 3 AND up_count = 0 AND down_count = 0'
```

> **v3 的 `read_count` / `recall_count` / 沉浮在 v4 没有**——v4 不回写"被读 / 被召回"。DSL 字段只剩顶踩计数 + credence + position_count + 时间。

## 输出 — Markdown(默认)

`````markdown
# search `回答风格` · 3/3

### [CARD] `card_01jz8k2m` · 3 answers · credence +6
**Q:** 用户偏好什么回答风格?
**A:** 默认简洁、要点优先

### [INSIGHT] `insight_01jx...`
用户在调试场景偏好先给定位再给改法

### [SESSION] `sess-...` · 2 hits · claude-code
- _[#17 human]_ 你回答时能不能先给结论？
`````

#### 约定

- 一条混合流,每条按 `kind` 渲不同块头:`[CARD]` / `[INSIGHT]` / `[SESSION]`。
- `[CARD]`:`**Q:**` 整段 `issue`;`**A:**` 当下答案的 `claim`(没答案时标 `(no answer yet)`)。
- `[INSIGHT]`:块头 + insight 正文。
- `[SESSION]`:块头(命中数 + source)+ 每个命中轮次一行摘录 `- _[#<idx> <role>]_ <text>`。

## 输出 — JSON(`--json`)

`cards` 是一条混合流(键名不变,每条带 `kind`):

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
      "top_position": {"position": "p1", "claim": "默认简洁、要点优先",
                       "credence": 6, "up_count": 7, "down_count": 1, "neutral_count": 0},
      "relevance": 0.82,
      "created_at": "2026-06-18T14:30:00Z"
    },
    {"kind": "insight", "insight_id": "insight_01jx...",
     "insight": "用户在调试场景偏好先给定位再给改法", "relevance": 0.61},
    {"kind": "session", "session_id": "sess-...", "source": "claude-code",
     "round_count": 42, "hit_count": 2,
     "hits": [{"index": 17, "role": "human", "text": "你回答时能不能先给结论？", "score": 0.55}],
     "relevance": 0.55}
  ]
}
```

`kind` 区分形态:`card` 带 `top_position`(`position_count=0` 时为 `null`);`session` 带 `hits` 摘录。看一张卡全部答案走 [`read <card_id>`](read.md);看整段 session 走 `read <sess-…>`。

## 错误

| 情况 | 行为 |
|---|---|
| `--where` DSL 语法错 / 未知字段 | `error: <detail>`,exit 1 |
| `--limit` 超出 `[1,200]` | `error: limit out of range`,exit 1 |

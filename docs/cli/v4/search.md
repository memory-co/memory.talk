# search

有意识检索:拿 query 撞**问题 + 答案**(`issue` + `claim`),返回匹配的卡,每张带它**最相关 / 当下的答案**(claim 命中取该答案,否则取现算 credence 最高的)。

```bash
memory.talk search <query> [--where '<DSL>'] [--limit N] [--json]
```

调 [`POST /v4/search`](../../api/v4/search.md)。跟 [`recall`](recall.md) 的区别:recall 是 hook 阶段无意识注入;search 是主动检索(带 query + DSL)。

## 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `<query>` | 是(可空串 `""`) | 撞 `issue` / `claim` 的检索词;空串 = 纯按 `--where` 过滤 |
| `--where` | 否 | DSL 过滤(见下) |
| `--limit` | 否,默认 `20`,上限 `200` | 返回多少张卡 |

## 排序

- `query` 非空:按**检索相关性**(向量 + FTS)排。**v4 无沉浮公式**——相关性只在这一刻算,不掺存储热度。
- `query` 空:按 `created_at` 倒序。
- 卡内取现算 `credence` 最高的答案作"当下答案"(平手按最近 review 时间)。

## `--where` DSL

作用在卡的**当下答案 + 卡元数据**上:

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
# search `回答风格`

3 results

---

### [CARD] `card_01jz8k2m` · `credence +6 · ↑7 ↓1 ·0` · 3 answers

**Q:** 用户偏好什么回答风格?
**A:** 默认简洁、要点优先

`scope: 日常问答;调试场景另说` · 2026-06-18 14:30

---

### [CARD] `card_01jzp3nq` · `(no answer yet)` · 0 answers

**Q:** 缓存层选 Redis 还是本地?

`2026-05-25 14:21`
`````

#### 约定

- 每张卡一个 H3 块:`### [CARD] \`<card_id>\` · \`credence <分> · ↑<up> ↓<down> ·<neutral>\` · <N> answers`。
- `**Q:**` 整段 `issue`;`**A:**` 当下答案的 `claim`(没答案时标 `(no answer yet)`,A 行不出)。
- 再一行 `scope`(空不出)+ 时间。
- 块间 `---`;末尾命中数 > 返回数时追 `_(showing N of TOTAL — pass --limit higher)_`。

## 输出 — JSON(`--json`)

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

`top_position` 是当下答案(`position_count=0` 时为 `null`)。看一张卡全部答案走 [`read <card_id>`](read.md)。

## 错误

| 情况 | 行为 |
|---|---|
| `--where` DSL 语法错 / 未知字段 | `error: <detail>`,exit 1 |
| `--limit` 超出 `[1,200]` | `error: limit out of range`,exit 1 |

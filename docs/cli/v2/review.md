# review

**导航哪些 session 有 recall 历史**,以及钻进单个 session 看每一轮的 recall 详情。AI 在思考过程中需要"看一眼最近哪些会话被自动召回过、上次召回的 query 是什么、那一轮抽了哪几张卡"时调这两个子命令。

跟 [`recall`](recall.md) 的差别:
- `recall` 是**写入路径**(每次调一次都新增一轮 round + 写 hit 记录)
- `review` 是**纯只读路径**(`SELECT`,不动数据,不影响 dedup 状态)

跟 [`log`](log.md) 的差别:
- `log` 看**单个对象**的全生命周期事件(imported / card_extracted / linked / tag_added 等业务事件)
- `review` 看 recall 维度的活动 —— 哪些 session 被召回过,以及每一轮抽了什么

```
memory-talk review
├── list                              # 横扫所有有 recall 历史的 session
└── detail <session_id>               # 钻进单个 session 看每一轮的 hit 详情
```

---

## review list

```bash
memory-talk review list [--limit N] [--data-root PATH] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--limit` | 100 | 返回最近活跃的前 N 个 session(按 `last_at` 倒序)|
| `--data-root` | `~/.memory-talk` | 数据根目录 |
| `--json` | 关 | 输出 JSON 而非 Markdown |

### 数据来源

直接 SQL 查 `recall` 表 + LEFT JOIN 聚合 `recall_hit` + LEFT JOIN `sessions` 判断该 session 在 sessions 表里存不存在。**O(1) 个查询、不动文件层、不加任何存储字段**。

```sql
SELECT
  r.session_id, r.round_count, r.first_at, r.last_at, r.last_query,
  COUNT(DISTINCT h.card_id) AS cards_injected,
  CASE WHEN s.session_id IS NOT NULL THEN 1 ELSE 0 END AS session_exist
FROM recall r
LEFT JOIN recall_hit h USING(session_id)
LEFT JOIN sessions s   ON s.session_id = r.session_id
GROUP BY r.session_id
ORDER BY r.last_at DESC
LIMIT ?;
```

`recall` 表本身就是"每个 session 一行 + atomic round counter",GROUP BY 只是顺手补 `cards_injected` 这个去重后的命中数。详见 [recall.md 的表设计章节](recall.md#去重-forward-reference)。

**`session_exist` 字段不持久化**,完全靠 `LEFT JOIN sessions` 实时算出。字段名直接对齐 SQL 真相(`sessions` 表里有没有这一行),不引入额外语义。理由:
- recall 跟 sessions 写入是两条独立路径 —— recall 时 session 大概率还没被 POST 到 `/v2/sessions`(所以 `sessions.session_id` 没这一行)。后续被任何调用方写入(常见触发是 [`sync`](sync.md) CLI 命令,但 `/v2/sessions` 是开放 endpoint,别的工具直接 POST 也行)之后,这个字段就翻 true。
- 这个状态会**自然演化**(false → true),持久化反而会跟真实状态漂移
- JOIN 一次的代价远小于"持久化 + 维护一致性"的代价

### Markdown(默认)

````markdown
# Sessions with recall history (3)

- **`sess_lancedb-discuss`** · `session_exist=true` · 12 rounds · 8 cards · last 2026-04-29T10:23:45Z
  > 怎么处理 LanceDB 的 FTS 索引重建

- **`sess_async-pool-debug`** · `session_exist=false` · 5 rounds · 4 cards · last 2026-04-29T09:01:12Z
  > 异步连接池为什么会死锁

- **`sess_arch-review`** · `session_exist=true` · 23 rounds · 14 cards · last 2026-04-28T22:00:00Z
  > 这个模块的依赖反向了吗
````

约定:
- 标题 `(N)` 是返回的 session 数。
- 每个 session 一行项目符号,字段顺序:
  1. **加粗反引号 session_id** —— 主导航 key,AI 拿到直接喂给后续 `view` / `log` / `recall` / `review detail`
  2. **`session_exist=true` / `session_exist=false`** —— 该 session 是否在 sessions 表里(LEFT JOIN sessions 算出):
     - `=true`:sessions 表里有这一行,**`view sess_xxx` / `log sess_xxx` 都可用**
     - `=false`:sessions 表里没这一行 —— 这条 session 只在 recall 路径上写过记录,还没人调过 `/v2/sessions` 把它写入。**此时 `view` / `log` 会 404**(`review detail` 不受影响,它读的是 recall 表)
  3. `<round_count> rounds` —— 这个 session 跑了多少次 recall
  4. `<cards_injected> cards` —— 去重后实际注入过 LLM context 的 card 数
  5. `last <ISO 时间>` —— 最近一次 recall 时间
- 紧跟一行 `> <last_query>` —— blockquote 格式,把最近一次的 prompt 作为"这个 session 在干嘛"的语义提示
- 空结果(从来没跑过 recall):

  ````markdown
  # Sessions with recall history (0)

  *(no recall history yet — call `memory-talk recall <session_id> <prompt>` first)*
  ````

### JSON(`--json`)

```json
{
  "sessions": [
    {
      "session_id": "sess_lancedb-discuss",
      "session_exist": true,
      "round_count": 12,
      "cards_injected": 8,
      "first_at": "2026-04-25T14:00:00Z",
      "last_at": "2026-04-29T10:23:45Z",
      "last_query": "怎么处理 LanceDB 的 FTS 索引重建"
    },
    {
      "session_id": "sess_async-pool-debug",
      "session_exist": false,
      "round_count": 5,
      "cards_injected": 4,
      "first_at": "2026-04-28T20:00:00Z",
      "last_at": "2026-04-29T09:01:12Z",
      "last_query": "异步连接池为什么会死锁"
    }
  ]
}
```

字段:
- `session_id`:带 `sess_` 前缀的 id
- **`session_exist`**:这个 session 在 sessions 表里有没有(`LEFT JOIN sessions` 实时算出)。`true` 时 `view` / `log` 可用;`false` 时只有 recall 维度的数据。
- `round_count`:这个 session 总共跑了几次 recall
- `cards_injected`:去重后实际进过 LLM 的 card 数
- `first_at` / `last_at`:第一次 / 最近一次 recall 时间
- `last_query`:最近一次 recall 的 prompt

---

## review detail

钻进单个 session,按时间倒序列出每一轮 recall 的 query 和命中的 cards。

```bash
memory-talk review detail <session_id> [--limit N] [--data-root PATH] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `<session_id>` | 必填 | raw 或带 `sess_` 前缀的 id;服务端自动加前缀 |
| `--limit` | 50 | 最近 N 轮(按 round_count 倒序)|

### 数据来源

```sql
-- 头部聚合(同 list 但加 session_id 过滤)
SELECT
  r.session_id, r.round_count, r.first_at, r.last_at, r.last_query,
  COUNT(DISTINCT h.card_id) AS cards_injected,
  CASE WHEN s.session_id IS NOT NULL THEN 1 ELSE 0 END AS session_exist
FROM recall r
LEFT JOIN recall_hit h USING(session_id)
LEFT JOIN sessions s   ON s.session_id = r.session_id
WHERE r.session_id = ?
GROUP BY r.session_id;

-- 每轮 hit 详情
SELECT round_count, query, recalled_at, card_id, rank
FROM recall_hit
WHERE session_id = ?
ORDER BY round_count DESC, rank ASC
LIMIT ?;     -- LIMIT 是行数(可能跨 round),实际渲染时按 round 分组
```

### Markdown(默认)

````markdown
# `sess_lancedb-discuss` · session_exist=true

12 rounds · 8 cards (deduped) · first 2026-04-25T14:00:00Z · last 2026-04-29T10:23:45Z

## Round 12 · 2026-04-29T10:23:45Z

> 怎么处理 LanceDB 的 FTS 索引重建

1. `card_01jz8k2m`
2. `card_01jzq7rm`
3. `card_01jzp3nq`

---

## Round 11 · 2026-04-29T09:50:01Z

> LanceDB 的 vector index 怎么调参

1. `card_01jzaaa`
2. `card_01jzbbb`

---

## Round 10 · 2026-04-28T22:30:11Z

> 选 ANN 还是 IVFFlat

1. `card_01jzccc`
````

约定:
- H1:session 头,带 `session_exist=` 标签
- 第二行紧跟一行**总览**:`<round_count> rounds · <cards_injected> cards (deduped) · first ... · last ...`
- 每个 round 一个 H2 + blockquote 的 query + 编号列表的 hit cards,中间用 `---` 分隔
- 编号 `1. 2. 3.` 就是 hit 的 rank(已经按 rank 升序)
- 倒序展示(round_count 大的在前,最近的最先看到 —— 跟 search results 同样的"最近的最有用"原则)
- 没找到 session(从来没 recall 过)→ 报错:`**error:** session not found in recall log`,exit 1

### JSON(`--json`)

```json
{
  "session_id": "sess_lancedb-discuss",
  "session_exist": true,
  "round_count": 12,
  "cards_injected": 8,
  "first_at": "2026-04-25T14:00:00Z",
  "last_at": "2026-04-29T10:23:45Z",
  "last_query": "怎么处理 LanceDB 的 FTS 索引重建",
  "rounds": [
    {
      "round_count": 12,
      "query": "怎么处理 LanceDB 的 FTS 索引重建",
      "recalled_at": "2026-04-29T10:23:45Z",
      "hits": [
        {"card_id": "card_01jz8k2m", "rank": 1},
        {"card_id": "card_01jzq7rm", "rank": 2},
        {"card_id": "card_01jzp3nq", "rank": 3}
      ]
    },
    {
      "round_count": 11,
      "query": "LanceDB 的 vector index 怎么调参",
      "recalled_at": "2026-04-29T09:50:01Z",
      "hits": [
        {"card_id": "card_01jzaaa", "rank": 1},
        {"card_id": "card_01jzbbb", "rank": 2}
      ]
    }
  ]
}
```

`rounds` 数组按 `round_count` 倒序。

---

## 副作用(共同)

- 只读 `recall` + `recall_hit` 表(detail 还 LEFT JOIN sessions)
- **不动 dedup 状态**(被去重的卡不会因此"复活")
- **不写 search_log / event_log / 任何文件**
- **不刷新 TTL** —— review 是元层面的访问,不算"用了 card"

## 错误(共同)

| 情况 | 行为 |
|---|---|
| `--limit` ≤ 0 | 400, `limit out of range` |
| `review detail` 的 session_id 在 recall 表不存在 | 404, `session not found in recall log` |
| server 处于 `rebuilding` | 503(其它命令同款 gate) |

## 跟 sessions 写入 / rebuild 的关系

- **sessions 写入路径**(`POST /v2/sessions`,通常通过 `sync` CLI 命令触发,但任何调用方都可以直接 POST):写 sessions 表,跟 recall 表正交。review 的 `session_exist` 字段就是 LEFT JOIN sessions 算出来的 —— 一条 session 被写入之前 `=false`,之后翻 `=true`,**review 命令本身不做任何事**,数据库 join 自动反映新状态。
- `rebuild` **会清空 recall + recall_hit**(SQLite-only 的代价,见 [recall.md 副作用](recall.md#副作用))。rebuild 之后跑 review 会暂时返回空列表,直到下一次 recall 把数据重新填进来。注意 sessions 表会被 rebuild **从文件层重建**,所以 `session_exist` 的值在 rebuild 后仍是真实的。

## 推荐姿势

```bash
# AI 进会话开头自检一下"我最近在想哪些事情"
memory-talk review list --limit 5

# 看到某个 session 有兴趣 → 钻进去看每一轮抽了什么
memory-talk review detail sess_lancedb-discuss

# 该 session session_exist=true → log/view 都可用
memory-talk log sess_lancedb-discuss

# session_exist=false → log/view 会 404
# 但 review detail 仍然能看 recall 维度的历史
# 也可以接着做一次 recall 拉新内容
memory-talk recall sess_async-pool-debug "现在又踩到了什么坑"

# 等 /v2/sessions 被写入之后(`sync` 是常见触发途径),session_exist 自动翻 true
memory-talk sync
memory-talk review list        # async-pool-debug 现在应该是 session_exist=true
```

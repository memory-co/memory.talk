# search

v3 主检索入口。hybrid FTS + 向量检索 + 元数据 DSL 过滤,结果分两支返回(cards 和 sessions)。命中的 `card_id` / `session_id` 直接返回给调用方——拿到就能喂给 `read`。

```bash
memory-talk search <query> [--where DSL] [--top-k N] [--json]
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `<query>` | — | 检索文本。可为空字符串(配合 `--where` 做纯元数据过滤) |
| `--where`, `-w` | 无 | 元数据过滤 DSL |
| `--top-k` | `settings.search.default_top_k`(默认 10) | 每支(cards / sessions)的上限 |
| `--json` | 关 | 输出 JSON 而非默认 Markdown |

## Markdown(默认)

````markdown
# search: LanceDB 选型

`search_id=sch_01K7XABC`

## cards (2)

### 1. CARD `card_01jz8k2m`

**Insight:** 选定 LanceDB 做向量存储

**Snippets:**

- ...**LanceDB** is a fully managed embedded vector database...
- ...vs Pinecone vs Chroma — **LanceDB** wins for embedded use case...

### 2. CARD `card_01jzp3nq`

**Insight:** LanceDB 落地后的踩坑清单

**Snippets:**

- ... NFS 上 mmap **LanceDB** 文件 ...

## sessions (1)

### 1. SESSION `sess_187c6576`

**Snippets:**

- ...讨论 **LanceDB** 零依赖...
- ...选型决策 **LanceDB** 替代了原本想用的 Pinecone...

**Source:** claude-code
````

约定:
- 每个结果的标题形如 `### N. CARD \`<card_id>\`` / `### N. SESSION \`<sess_id>\``,大写类型字样 + 反引号包住 id,渲染后类型和 id 都最显眼,不用再扫细节。
- 每个结果下面都用 **加粗 inline 标签**(`**Insight:**` / `**Snippets:**` 等)分小节,渲染前后都好读 —— 标签自带分段语义,不依赖颜色和排版。
- card 的元信息是 `Insight`(必有,顶部);session 顶部只放 `Snippets`,**`Source` 弱信号、放结果末尾**——同一份 corpus 里 Source 大都重复(`claude-code` / `codex` 占绝大多数),扫读时把它放最显眼位置反而干扰。
- `Snippets` 是一个无序列表(`- ...`),每条 snippet 一行。`**...**` 是 highlight 标记,跟 API 返回保持一致。
- `score` 不在 Markdown 输出里 —— hybrid RRF 的分数对人类读者价值低,反而干扰扫读。仍然保留在 `--json` 响应里供脚本 / 调试用。
- 空命中桶仍然出 header(`## cards (0)`),不打"no results"占位文字。

## JSON(`--json`)

```json
{
  "search_id": "sch_01K7XABC...",
  "query": "LanceDB 选型",
  "cards": {
    "count": 2,
    "results": [
      {
        "card_id": "card_01jz8k2m",
        "rank": 1,
        "score": 0.0312,
        "insight": "选定 LanceDB 做向量存储",
        "snippets": ["...**LanceDB**..."]
      }
    ]
  },
  "sessions": {
    "count": 1,
    "results": [
      {
        "session_id": "sess_187c6576",
        "rank": 1,
        "score": 0.0289,
        "source": "claude-code",
        "snippets": ["...讨论 **LanceDB** 零依赖..."]
      }
    ]
  }
}
```

注意：
- 返回体里的 `card_id` / `session_id` 都是**带前缀的裸 id**,直接喂给 `read` 即可,不需要任何中间转换。
- `search_id` 是本次查询的**审计 id**——只出现在服务端 `search_log` 表里,**不用于任何后续读取**。
- `rank` 从 1 开始,对齐 `results` 数组位置。

## 排序

默认按一个**单一公式**给所有结果打 final score,不分 `--sort hot/new/top` 多档模式。公式同时吃 query 相关度和 card 的论坛信号(stats + age),让"既相关又被讨论得扎实"的 card 自然浮到上面。

变量(供公式使用):

- `relevance` — hybrid(FTS + 向量)RRF 相关度分;query 为空时全部置 0
- `review_up` / `review_down` / `review_neutral` / `review_count` / `read_count` / `recall_count` — card.stats 各字段;sessions 桶没有这些,统一按 0 处理
- `age_days` — 距 `created_at` 的天数

默认公式(配在 `settings.search.ranking_formula`,可改):

```
relevance + 0.1 * (review_up - review_down) + 0.02 * log(read_count + 1) - 0.005 * age_days
```

公式只走 settings,**不进 CLI 参数** —— 论坛动力学是系统级偏好,不该每次 search 都重调。想"只按相关度"就改成 `relevance`,想纯 Reddit hot 就改成 `(review_up - review_down) / pow(age_days + 2, 1.5)`,长什么样取决于你怎么想"沉浮"。

临时只想看某个切片(shadow / 高争议 / 新建未读)走 `--where` 过滤,默认公式跑出来的顺序在这个子集内自然合理 —— 详见下面 DSL 示例。

## 追踪语义

每次 search 都会在服务端 `search_log` 表 + `logs/search/<UTC 日期>.jsonl` 里追加一条——**存的是完整的响应体**(含 `snippets` / `score` / `insight` 等一切呈现给使用者的内容),不是只存命中 id。这样事后审计能完整复原"当时用户看到了什么",即便后续索引变了、对象被改了也能追回原样。

这是**纯审计**——不做"凭据发行",不参与任何后续调用的校验。想看"这次 AI 会话用了哪些数据"——看 AI 自己的 tool-use 对话记录(sync 之后存成一个 session),那里有每次 `read` / `search` 的输入输出原文。服务端不再造重复的追踪层。

search_log 默认永久保留。老化策略见 `settings.search.search_log_retention_days`。

## DSL

支持字段:

- 元数据:`session_id`、`card_id`、`source`、`created_at`
- card 论坛信号(只对 cards 桶有意义,sessions 桶上访问报错):`review_up`、`review_down`、`review_neutral`、`review_count`、`read_count`、`recall_count`

运算符:`=`、`!=`、`<`、`>`、`<=`、`>=`、`LIKE`、`IN`、`NOT IN`、`AND`。

示例:

```bash
memory-talk search "LanceDB" -w 'source = "claude-code"'
memory-talk search "" -w 'created_at > "2026-04-01"'
memory-talk search "bug" -w 'session_id = "sess_abc123"'

# shadow knowledge:被路过得多但没人真讨论过的 card
memory-talk search "" -w 'read_count > 10 AND review_count = 0'

# 高争议:赞踩都不少
memory-talk search "" -w 'review_up >= 3 AND review_down >= 3'

# 被反驳更多的 card(可能要 fork)
memory-talk search "" -w 'review_down > review_up'
```

DSL 解析失败:

````markdown
**error:** DSL parse error: unknown field 'foo'
````

`--json` 模式下:

```json
{"error": "DSL parse error: unknown field 'foo'"}
```


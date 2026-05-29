# Search API

## POST /v3/search

v3 主检索入口。hybrid FTS + 向量检索 + 元数据 / stats DSL 过滤,**card 和 session 进同一个沉浮公式融合排序** —— 返回**单一**`results[]` 数组,按 final score 降序。session 内部按 round 行级召回,同 session 多 round 命中聚合到一个 result(`hits[]`)。

命中条目直接带前缀化 id(`card_<ULID>` / `sess_<ULID>`),拿到就能喂给 `POST /v3/read`。

CLI 对应 [`search`](../../cli/v3/search.md) 命令。

### 请求体

```json
{
  "query": "LanceDB 选型",
  "where": "review_count = 0 AND read_count > 10",
  "top_k": 10
}
```

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `query` | 是 | — | 检索文本;**可空字符串**(配合 `where` 做纯元数据 / stats 过滤) |
| `where` | 否 | 无 | DSL,见下方 |
| `top_k` | 否 | `settings.search.default_top_k`(默认 10) | **总**结果数上限(card + session 合计) |
| `recall_mode` | 否 | `false` | 0.8.x 新增。`true` 时切到 recall 视角:cards-only、跳过 `ranking_formula`、按裸 RRF 排序。**只读** —— 不写 `recall_log`,不 bump `recall_count`。CLI 对应 `--recall` |
| `recall_session_id` | 否 | `null` | 仅在 `recall_mode=true` 下有意义:模拟该 session 的 `recall_log` dedup。CLI 对应 `--session` |

### 响应

```json
{
  "search_id": "sch_01K7XABC...",
  "query": "LanceDB 选型",
  "mode": "search",
  "session_id": null,
  "count": 4,
  "results": [
    {
      "type": "card",
      "rank": 1,
      "score": 0.52,
      "card_id": "card_01jz8k2m",
      "insight": "选定 **LanceDB** 做向量存储,主要因为零依赖嵌入式架构",
      "stats": {
        "review_up": 7,
        "review_down": 3,
        "review_neutral": 2,
        "review_count": 12,
        "read_count": 42,
        "recall_count": 18
      }
    },
    {
      "type": "session",
      "rank": 2,
      "score": 0.42,
      "session_id": "sess_187c6576",
      "source": "claude-code",
      "hit_count": 8,
      "hits_shown": 3,
      "hits": [
        {
          "index": 11,
          "role": "human",
          "text": "我看 **LanceDB** 是个不错的选择,零依赖",
          "score": 0.38,
          "context_before": {"index": 10, "role": "human", "text": "我们要选个向量库,纠结"},
          "context_after": {"index": 12, "role": "assistant", "text": "好的,那就 LanceDB 了"}
        },
        {
          "index": 15,
          "role": "assistant",
          "text": "嵌入式部署最方便,**LanceDB** 跟应用一起走,不用起额外服务",
          "score": 0.31,
          "context_before": {"index": 14, "role": "human", "text": "用什么部署?"},
          "context_after": {"index": 16, "role": "human", "text": "OK 就这么定"}
        }
      ]
    },
    {
      "type": "card",
      "rank": 3,
      "score": 0.38,
      "card_id": "card_01jzp3nq",
      "insight": "**LanceDB** 落地后的踩坑清单",
      "stats": {
        "review_up": 2,
        "review_down": 0,
        "review_neutral": 0,
        "review_count": 2,
        "read_count": 5,
        "recall_count": 1
      }
    }
  ]
}
```

完整字段定义和落库快照(SearchLog)见 [`../../structure/v3/search-result.md`](../../structure/v3/search-result.md)。

### 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `search_id` | string | `sch_<ULID>`,审计 id |
| `query` | string | 回显请求 |
| `mode` | `"search"` / `"recall"` | 0.8.x 新增。`search` 是正常路径;`recall` 是 `recall_mode=true` 的调试视角(cards-only + 裸 RRF + 可选 dedup) |
| `session_id` | string\|null | 0.8.x 新增。仅 `mode=recall` 且请求带 `recall_session_id` 时不为 null,回显 dedup 作用域 |
| `count` | int | `results[]` 长度(`== top_k` 时说明被截断) |
| `results` | object[] | 混合 card / session,按 `score` 降序 |

### results[] 共有字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `"card"` 或 `"session"`,**discriminator** |
| `rank` | int | 1-based |
| `score` | float | final score(沉浮公式跑完);跨 type 直接可比 |

### type = "card" 专属字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `card_id` | string | 带前缀 |
| `insight` | string | card 的洞见**整段** —— 已对匹配关键词内联 `**keyword**` 高亮(FTS 命中在 `card.rounds[].text` 而**不在** `insight` 时 → 整段无高亮,但 card 仍返回) |
| `stats` | Stats | 当前 stats 快照,详见 [talk-card.md#Stats](../../structure/v3/talk-card.md#stats) |

> **没有独立 `snippets` 字段** —— `insight` 已经是蒸馏后的一句话,够短,直接给整段加高亮比抽片段更直观。要看完整 `rounds` 走 `POST /v3/read`。

### type = "session" 专属字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 带前缀 |
| `source` | string | 平台来源(`claude-code` / `codex`) |
| `hit_count` | int | 本 session 里命中的 round **总数** |
| `hits_shown` | int | `hits[]` 实际长度(≤ `hit_count`,默认上限 3) |
| `hits` | Hit[] | 每条命中 round 的窗 |

### Hit(`hits[]` 元素)

| 字段 | 类型 | 说明 |
|---|---|---|
| `index` | int | round 在 session 内的稳定编号 |
| `role` | string | `human` / `assistant` / `tool` / `system` |
| `text` | string | round 原文,含 `**keyword**` 高亮 |
| `score` | float | round 级 RRF 检索分(**跟外层 session-level `score` 是不同尺度**) |
| `context_before` | object\|null | 前一条 round `{index, role, text}`;**长内容截断到 200 字**;`null` 表示是第一条 |
| `context_after` | object\|null | 后一条 round;`null` 表示是最后一条 |

### 召回粒度

| 召回管道 | 单元 | 一个 result 对应 |
|---|---|---|
| card 召回 | card 整体(FTS 打 `insight` / `rounds[].text`,向量打 `insight`) | 一张 card;响应里 `insight` 整段返回,匹配 keyword 内联 `**...**` 高亮 |
| session 召回 | **session round 行**(FTS / 向量分别打 `rounds[].text`) | 一个 session,**多 round 命中聚合到 `hits[]`** |

两类候选**走同一个 `ranking_formula`** 算 final score,**混合排序**。card 自带 stats(`review_up` 等),session 这些项统一置 0。这意味着:

- **全新没 review 的 card** 跟同等相关度的 session **公平竞争**,不强制 card 优先
- **被讨论扎实的老 card** 自然超过相关度相近的新 session
- **多 round 命中的 session** 通过聚合 `relevance` 获得高分(本质上等价于"多次命中加分")

详细公式 + 变量见 [#排序](#排序)。

### 返回体规则

- `card_id` / `session_id` 是**带前缀的裸 id**,直接喂给 `POST /v3/read`
- `search_id` 只是审计 id,不参与任何后续读取校验
- card 响应**不展开** `reviews` / `source_cards`(走 `read` 看)
- session 响应**没有** `tags` / `links`(v3 无这两个概念)
- session `hits[]` 默认按 RRF round score 降序,**不**按 round index 顺序
- 相邻 round 都命中(`#N` / `#N+1`)→ **生成两个独立 hit**,不去重;两个窗的 `context_before/after` 会出现内容重叠(feature)
- search 本身**不修改任何对象**(不刷新 stats / 不增加 read_count) —— search 是"决定看什么",真"看了"用 read

### 副作用

- 在服务端 `search_log` 表 + `~/.memory.talk/logs/search/<UTC 日期>.jsonl` 追加一条 SearchLog,**存的是完整响应体**(含 `results[]` 全字段,session hits 含上下文窗)
- **不刷新任何 stats**

### 排序

`settings.search.ranking_formula` 是单一公式,**统一应用到所有候选(card + session)**。

变量:

- `relevance` —— RRF 相关度;cards 是 `max/avg` over `insight`/`rounds` matches;sessions 是按 hits 聚合(默认衰减聚合)
- `review_up` / `review_down` / `review_neutral` / `review_count` / `read_count` / `recall_count` —— card.stats;**sessions 全部置 0**
- `age_days` —— 距 `created_at` 的天数

**0.8.x 默认公式**:

```
relevance
```

即裸 RRF 相关度,不掺 stats。理由:`search` 是主动调用,query 多为关键词 / identifier,用户意图是"找最相关的",不应被路过型 stats 信号反超(详见 [`../../report/2026-05-30-search-vvp-ai-hyphen-identifier.md`](../../report/))。

要回到论坛动力学排序,改 settings:

```
relevance + 0.1 * (review_up - review_down) - 0.005 * age_days
```

跨 type 可比性:两类候选过同一公式,session 的 stats 项天然为 0。默认 `relevance` 下,sessions 跟 cards 在裸 RRF 同尺度上比较。

### `recall_mode=true` 的排序差异

跟 `mode=search` 相比,`recall_mode=true` **跳过 `ranking_formula` 整个评估**,直接用 cards 的 `relevance`(裸 RRF)排序。**即使用户自定义了 `ranking_formula`,recall 视角也不应用** —— 这是设计上的"recall 一定是裸 RRF"硬约束(跟 `service/recall.py` 行为对齐)。

### DSL

支持字段:

- 类型:`type`(`"card"` / `"session"`)—— 切片到单一类型
- 元数据:`session_id`、`card_id`、`source`、`created_at`
- card 论坛信号(只对 cards 应用,sessions 上访问报错):`review_up`、`review_down`、`review_neutral`、`review_count`、`read_count`、`recall_count`

运算符:`=` / `!=` / `<` / `>` / `<=` / `>=` / `LIKE` / `IN` / `NOT IN` / `AND`(无 `OR`)

#### 字段应用域规则

DSL 某字段如果不属于当前候选类型 → **这个候选整条过滤掉**:

- `review_count = 0` → 只保留 cards
- `source = "claude-code"` → 只保留 sessions
- `created_at > "..."` → cards 和 sessions 都按各自的 `created_at` 过滤
- `type = "card"` → 显式切片

示例:

```bash
# shadow knowledge:被路过得多但没人真讨论过的 card(自动切到 cards-only)
{"query": "", "where": "read_count > 10 AND review_count = 0"}

# 高争议
{"query": "", "where": "review_up >= 3 AND review_down >= 3"}

# 被反驳更多
{"query": "", "where": "review_down > review_up"}

# 只看 card
{"query": "LanceDB", "where": "type = \"card\""}

# 只看 session
{"query": "LanceDB", "where": "type = \"session\""}
```

### 错误

| 情况 | 状态 |
|---|---|
| `where` DSL 解析失败 | 400, `DSL parse error: <details>` |
| `where` 引用未知字段 | 400, `unknown field: <name>` |
| `top_k` 超过服务端硬上限(默认 100) | 400 |
| `query` 非字符串 | 400 |
| `ranking_formula` 编译错 | 500, `ranking formula compile error: <details>` |

### 跟 v2 的差异

| | v2 | v3 |
|---|---|---|
| 响应结构 | `cards: {count, results}` + `sessions: {count, results}` 两支 | **单一** `results[]`,`type` 字段做 discriminator |
| 排序 | 两支独立 RRF 排序;UI 拼接 | **统一公式**算 final score 后混合降序 |
| card 字段 | `summary` + `links` + `tags` + `snippets[]`(片段数组) | `insight`(整段直出 + 内联高亮)+ `stats`,**无独立 `snippets[]`** |
| session 字段 | `tags` + `links` + `snippets[]`(平铺) | `hit_count` + `hits_shown` + `hits[]`(窗结构) |
| 召回粒度 | session 整体一行 | session 内 round 行级,聚合到一个 session 的 hits[] |
| `top_k` 语义 | 每支 top_k(总 2×top_k) | **总** top_k(card + session 合计) |
| DSL 字段 | `session_id` / `card_id` / `tag` / `source` / `created_at` | 删 `tag`,加 `type` + 6 个 stats 字段 |
| DSL 运算符 | `=` / `!=` / `LIKE` / `IN` / `NOT IN` / `AND` | 加 `<` / `>` / `<=` / `>=` |
| `from_search_id` | 自动注入 card.created 事件 | 删 |

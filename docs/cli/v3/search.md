# search

v3 主检索入口。hybrid FTS + 向量检索 + 元数据 / stats DSL 过滤,**card 和 session 在同一个沉浮公式下融合排序** —— 返回**单一**结果流,按 final score 降序;card 像精炼洞见,session 像对话原文,谁在前由公式说了算。session 内部按 round 行级召回,多 round 命中聚合到同一 session 块,每个命中给前后一行上下文窗。

命中的 `card_id` / `session_id` 直接返回给调用方 —— 拿到就能喂给 `read`。

```bash
memory.talk search <query> [--where DSL] [--top-k N] [--all] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `<query>` | — | 检索文本。可为空字符串(配合 `--where` 做纯元数据 / stats 过滤) |
| `--where`, `-w` | 无 | 元数据 / stats / type 过滤 DSL,见 [#DSL](#dsl) |
| `--top-k` | `settings.search.default_top_k`(默认 10) | **总**结果数上限(card + session 合计) |
| `--all`, `-a` | 关 | 跳过 strong-floor 过滤(见下文),展示 top_k 全部结果 |
| `--json` | 关 | 输出 JSON 而非默认 Markdown |

### strong-floor 过滤(默认开)

排序之后再过一遍:**如果某类型(card / session)有强匹配,只保留强匹配;没有就全留**。阈值 hardcode,语义和值见 [`../../structure/v3/search-result.md#strong-floor-过滤`](../../structure/v3/search-result.md#strong-floor-过滤)。

过滤后的渲染会在末尾多一行 `_(N weak results hidden by strong-floor filter — pass --all to see)_`。要看被藏的内容 → `--all`。

`--all` 透传 server,**只影响渲染层是否进过滤**,不改召回 / 排序。

## 召回与排序

**两条召回管道**,合并到**一个排序**里:

| 召回管道 | 单元 | 出来后的"个体" |
|---|---|---|
| card 召回 | card 整体(FTS + 向量打 `insight` / `rounds[].text`) | 一个 card result |
| session 召回 | **session round 行**(FTS / 向量分别打 `rounds[].text`) | 一个 session result,**同 session 多 round 命中聚合到 `hits[]`**,每个命中带前后一行上下文 |

两类候选都经过同一个 `settings.search.ranking_formula` 算 final score,**混合按 score 降序排列**。card 自带 stats 信号(review_up / read_count 等),session 这些信号统一按 0 处理 —— 公式会自然让"被讨论得扎实"的 card 浮起来,但**全新没 review 的 card 跟同等相关度的 session 公平竞争**,不强制 card 优先。这是论坛动力学的核心:沉浮是涌现的,不是硬编码"卡先于会话"。

详细公式 + 变量见 [#排序](#排序)。

## Markdown(默认)

`````markdown
# search: LanceDB 选型

`search_id=sch_01K7XABC` · 4 results · 2 hidden

---

### [CARD] `card_01jz8k2m` · `↑7 ↓3 · reviews 12 · reads 42 · recalls 18` · 2026-04-10 22:30 (43 days ago)

选定 **LanceDB** 做向量存储,主要因为零依赖嵌入式架构

---

### [SESSION] `sess_187c6576` · claude-code · 3 hits

**#11, #13** · top score `0.0163` · 2026-04-10 22:32 (43 days ago)
````
[10 AI] 我们要选个向量库, 纠结
[11 HUMAN*] 我看 LanceDB 是个不错的选择, 零依赖
[12 AI] 好的, 那就 LanceDB 了
[13 AI*] 嵌入式部署最方便, LanceDB 跟应用一起走
[14 HUMAN] OK 就这么定
````

> 这里 hit #11 和 hit #13 idx 差 2,窗触碰 —— 合并到一个 fence,中间共享的 round [12] 只画一次。`top score` 取 cluster 里最高的(`#11` 的)。

---

### [CARD] `card_01jzp3nq` · `↑2 ↓0 · reviews 2 · reads 5 · recalls 1` · 2026-05-01 17:14 (22 days ago)

LanceDB 落地后的踩坑清单

---

_(2 weak results hidden by strong-floor filter — pass `--all` to see)_
`````

### 约定

#### 整体布局

- **单一结果流**,按 final score 降序混排 card 和 session。**没有**"## cards"/"## sessions"分组小标题。
- 顶部一行 `search_id=... · N results`,N 是 `results[]` 实际长度。
- 每个 result **都是 H3 标题** `### [TYPE] \`<id>\` · <metadata>`,中间用 `---` 分隔。`[TYPE]` 是 `[CARD]` / `[SESSION]` 字面前缀 —— 让混合流里的两种类型在同一层级出现、但一眼能分。

#### Card 块

- 标题:`### [CARD] \`<card_id>\` · \`<stats inline>\``。`[CARD]` 是固定字面标签(类比 Google 搜索结果里的 "Sponsored" / "Ad");stats 用反引号包成 inline code 跟 id 对齐;`↑N ↓N` 是 review_up / review_down,`X reviews` 是总数(含中立),`Y reads` / `Z recalls` 是"被路过"的两类信号。
- 标题下空一行,**整段 `insight` 直接展开**作为普通段落 —— 不加粗整段、不抽 snippet,只对**匹配的关键词**用 `**...**` 内联高亮。`insight` 本身已经是一句蒸馏后的话,够短,直出比抽片段更清楚。
- FTS 命中可能发生在 `card.rounds[].text` 里而**不在** `insight` 里 —— 这种情况 `insight` 段不出现任何高亮,但 card 仍照常展示;读者要看 round 原文走 `read card_xxx`。

#### Session 块

- 标题:`### [SESSION] \`<sess_id>\` · <source> · K hits`。`K` 是本 session 命中 round **总数**(可能多于实际展示数)。
- 每个命中(或一组合并后的相邻命中)是一个**渲染块**,形如:
  - 头一行:`**#<idx>** · score \`<X.XXXX>\` · <YYYY-MM-DD HH:MM> (<N units ago>)`
    - 多 hit 合并时变成 `**#<idxA>, #<idxB>** · top score \`<top X.XXXX>\` · <top hit 的时间>`
  - 接一段 fenced code block(```` ``` ````),按 idx 升序逐行 `[<idx> <ROLE>[*]] <text>`
    - `<ROLE>` 大写,`HUMAN` / `AI` / `TOOL` / `SYSTEM`(`AI` 是 server 端 `assistant` 的 CLI 显示别名)
    - `*` 标记原始 hit 行;纯上下文行不加 `*`
    - 文本里的 `\n` 在渲染时压成空格,fence 内每条 round 单行展示(原文结构走 `read`)
- 块之间空一行隔开,**不**用 `---`(那是 result 之间的分隔符,不混用)
- 每个 session **最多展示 3 个 hit**(`hits_shown` 上限),合并后块数 ≤ hit 数

#### 上下文窗规则

- **窗大小固定**:前 1 行 + 后 1 行,不可调
- 上下文行**纯 round 文本前缀**(超 200 字按字符截断到 200 + `…`)
- 上下文行**不过滤 role** —— tool / sidechain 也照常显示(它们是真实上下文的一部分)
- **相邻 hit 自动合并**:同一 session 里两个 hit 的 idx 差 `≤ 2`(窗触碰或重叠)→ 合并到一个 fence,union 所有涉及的 round,**每个 round 只画一次**。原本会重复出现的中间行(hit A 的 ctx_after 同时是 hit B 的 ctx_before)只保留一份。每个原始 hit 的主 idx 仍带 `*`
- 合并的 cluster 头按 idx 顺序列举所有命中(`#4, #5` 或 `#10, #11, #12`),score 和时间用 cluster 里**最强 hit** 的(语义上"这块最相关的位置")

#### 其它

- result 之间用 `---` 分隔(无论 card 还是 session)
- card / session 在标题里的 id 全部反引号包住
- `score` 在 Markdown 输出里露出(让读者眼测相对强弱)。注意这是 LanceDB RRF 融合分,典型 `0.01–0.03`,**只看排名不看绝对相似度**,详见 [`../../structure/v3/search-result.md#关于-rrf-分的一句忠告`](../../structure/v3/search-result.md#关于-rrf-分的一句忠告)
- 0 命中 → header 仍然出(`search_id=... · 0 results`),不打"no results"占位文字

## JSON(`--json`)

```json
{
  "search_id": "sch_01K7XABC...",
  "query": "LanceDB 选型",
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
        },
        {
          "index": 22,
          "role": "assistant",
          "text": "**LanceDB** 单文件能支持到 TB 级,够大多数本地场景了",
          "score": 0.27,
          "context_before": {"index": 21, "role": "human", "text": "容量上限呢?"},
          "context_after": {"index": 23, "role": "human", "text": "那很合适"}
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

### 字段

#### 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `search_id` | string | `sch_<ULID>`,审计 id |
| `query` | string | 回显请求 |
| `count` | int | `results[]` 长度(可能 ≤ `top_k`,等于 `top_k` 时说明被截断了) |
| `hidden_count` | int | 被 strong-floor 过滤切掉的条数;`--all` / `show_all=true` 时固定 `0` |
| `results` | object[] | 混合结果,按 `score` 降序排列 |

#### `results[]` 共有字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `"card"` 或 `"session"`,**discriminator**:决定后续字段长什么样 |
| `rank` | int | 1-based,对齐 `results[]` 位置 |
| `score` | float | **final score**(沉浮公式跑完);跨 card / session 直接可比 |

#### `type = "card"` 专属字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `card_id` | string | 带前缀 |
| `insight` | string | card 的洞见**整段** —— 已对匹配的关键词内联 `**keyword**` 高亮(FTS 命中在 `card.rounds[].text` 但不在 `insight` 时 → 整段无高亮,但 card 仍返回) |
| `created_at` | string | ISO 8601 UTC card 创建时间 |
| `stats` | Stats | 当前 stats 快照,详见 [`../../structure/v3/talk-card.md#Stats`](../../structure/v3/talk-card.md#stats) |

> 没有独立 `snippets` 字段 —— `insight` 已经是蒸馏后的一句话,够短,直出比再抽片段更清楚。要看完整 `rounds` 走 `read`。

#### `type = "session"` 专属字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 带前缀 |
| `source` | string | 平台来源 |
| `hit_count` | int | 本 session 里命中的 round **总数** |
| `hits_shown` | int | `hits[]` 实际长度(≤ `hit_count`,默认上限 3) |
| `hits` | Hit[] | 每条命中 round 的窗(见下方) |

#### Hit(`hits[]` 元素)

| 字段 | 类型 | 说明 |
|---|---|---|
| `index` | int | round 在 session 内的稳定编号 |
| `role` | string | `human` / `assistant` / `tool` / `system` |
| `text` | string | round 原文,含 `**keyword**` 高亮 |
| `score` | float | round 级 RRF 检索分(**不**是 session-level final score;不要混着比) |
| `timestamp` | string\|null | ISO 8601 UTC,本 round 在源平台发生的时间;部分老 round / adapter 可能 null |
| `context_before` | object\|null | 前一条 round `{index, role, text}`;长内容截 200;`null` 表示是第一条 |
| `context_after` | object\|null | 后一条 round;`null` 表示是最后一条 |

`context_before` / `context_after` 里的 `text` **可能也含 `**keyword**`** —— FTS 同样给上下文行加高亮(如果它恰好命中)。

### 注意

- 返回体里的 `card_id` / `session_id` 都是**带前缀的裸 id**,直接喂给 `read`
- `search_id` 是审计 id —— 只出现在服务端 `search_log` 表,**不用于任何后续读取**
- `rank` 跟 `score` 是 1-1 对应的;同分时按内部 ULID 次序稳定排序
- session 的 `score` 是聚合后的 final score;`hits[].score` 是单 round 的 RRF 分;**不是同一尺度**

## 排序

默认按一个**单一公式**给所有结果(card 和 session)打 final score,降序排列。公式同时吃 query 相关度和 card 的论坛信号(stats + age) —— 让"既相关又被讨论得扎实"的 card 自然浮到上面,但不强制 card 优先于 session。

变量(供公式使用):

- `relevance` —— hybrid(FTS + 向量)RRF 相关度分
  - cards 桶:`max(FTS over insight, FTS over rounds, vector over insight)` 之类的混合
  - sessions 桶:本 session 所有命中 round 的 RRF 分按 hits 聚合(默认 `1 - prod(1 - score_i)` 衰减聚合,backend 配置)
  - query 为空时全部置 0
- `review_up` / `review_down` / `review_neutral` / `review_count` / `read_count` / `recall_count` —— card.stats 各字段;**sessions 全部置 0**(session 本身没有论坛 stats)
- `age_days` —— 距 `created_at` 的天数

默认公式(配在 `settings.search.ranking_formula`,可改):

```
relevance + 0.1 * (review_up - review_down) + 0.02 * log(read_count + 1) - 0.005 * age_days
```

跨 card / session 的可比性来自:**两类候选都过同一公式**。card 有 stats 加分,session 这些项为 0 —— 全新没 review 的 card 跟同相关度的 session **公平竞争**,被讨论扎实的老 card 自然超过相关度相近的新 session。这是论坛动力学的核心。

公式只走 settings,**不进 CLI 参数** —— 想"只按相关度"就改成 `relevance`,想纯 Reddit hot 就改成 `(review_up - review_down) / pow(age_days + 2, 1.5)` —— 长什么样取决于你怎么想"沉浮"。

临时只想看某个切片(shadow / 高争议 / 只 card / 只 session)走 `--where` 过滤,默认公式跑出来的顺序在子集内自然合理 —— 详见下面 DSL 示例。

## 追踪语义

每次 search 都会在服务端 `search_log` 表 + `logs/search/<UTC 日期>.jsonl` 里追加一条 —— **存的是完整响应体**(含 `results[]` 全部字段,session hits 含完整上下文窗)。事后审计能复原"当时用户看到了什么",即便 sync 给 session 追加了新 round、card 拿到新 review 也能追回原样。

这是**纯审计** —— 不做"凭据发行",不参与任何后续调用的校验。

search_log 默认永久保留。老化策略见 `settings.search.search_log_retention_days`。

## DSL

支持字段:

- 类型:`type`(取值 `"card"` / `"session"`,**用来切片**到单一类型)
- 元数据:`session_id`、`card_id`、`source`、`created_at`
- card 论坛信号(只对 cards 应用,sessions 桶上访问报错):`review_up`、`review_down`、`review_neutral`、`review_count`、`read_count`、`recall_count`

运算符:`=`、`!=`、`<`、`>`、`<=`、`>=`、`LIKE`、`IN`、`NOT IN`、`AND`。

### 字段应用域

DSL 里某个字段如果**不属于**当前候选的类型,这个候选会被**整条过滤掉**:

- `where: 'review_count = 0'` → 只保留 cards(sessions 没有此字段)
- `where: 'source = "claude-code"'` → 只保留 sessions(cards 没有此字段)
- `where: 'created_at > "2026-04-01"'` → cards 和 sessions 都按各自的 `created_at` 过滤

想要"只看 card"或"只看 session"用 `type`:

```bash
memory.talk search "LanceDB" -w 'type = "card"'      # 只 cards
memory.talk search "LanceDB" -w 'type = "session"'   # 只 sessions
```

### 示例

```bash
memory.talk search "LanceDB" -w 'source = "claude-code"'
memory.talk search "" -w 'created_at > "2026-04-01"'
memory.talk search "bug" -w 'session_id = "sess_abc123"'

# shadow knowledge:被路过得多但没人真讨论过的 card
memory.talk search "" -w 'read_count > 10 AND review_count = 0'

# 高争议:赞踩都不少
memory.talk search "" -w 'review_up >= 3 AND review_down >= 3'

# 被反驳更多的 card(可能要 fork)
memory.talk search "" -w 'review_down > review_up'

# 只看 card
memory.talk search "LanceDB" -w 'type = "card"'

# 只看 session
memory.talk search "LanceDB" -w 'type = "session"'
```

DSL 解析失败:

````markdown
**error:** DSL parse error: unknown field 'foo'
````

`--json` 模式下:

```json
{"error": "DSL parse error: unknown field 'foo'"}
```

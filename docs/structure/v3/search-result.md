# Search Result

`POST /v3/search` 的**输出形态**和服务端审计落盘的**SearchLog 结构**。v3 的核心改变:**单一融合排序** —— card 和 session 进同一个 `ranking_formula` 算 final score 后混合降序;不再分 `cards`/`sessions` 两支。

## 输入

```json
{
  "query": "LanceDB 选型",
  "where": "review_count = 0 AND read_count > 10",
  "top_k": 10
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `query` | 是 | 检索文本;可空(配合 `where` 做纯元数据 / stats 过滤) |
| `where` | 否 | DSL,见 [`../../api/v3/search.md#DSL`](../../api/v3/search.md#dsl) |
| `top_k` | 否 | **总**结果数上限(card + session 合计),默认 `settings.search.default_top_k` |

## 输出

```json
{
  "search_id": "sch_01K7XABCDEFGHIJK01234",
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

## 召回模型

两条不同粒度的检索,**合并到一个排序**:

| 召回管道 | 单元 | 在 results[] 里对应 |
|---|---|---|
| card 召回 | card 整体(FTS / 向量打 `insight` + `rounds[].text`) | 一个 `type: "card"` 的 result;`insight` **整段返回**,匹配关键词内联 `**...**` 高亮,**无独立 snippets 字段** |
| session 召回 | **session round 行**(FTS / 向量分别打 `rounds[].text`) | 一个 `type: "session"` 的 result;**同 session 多 round 命中聚合到 `hits[]`**,每个 hit 带前后一行上下文窗 |

两类候选**共用同一个 `ranking_formula`** 算 final score → 单一 `results[]` 按 score 降序混排。card 自带 stats 信号(`review_up` 等),session 这些信号统一置 0 —— 自然偏序由公式涌现,而非硬编码"卡先于会话"。

UI 层(CLI Markdown 渲染)对两种 result 用**同一种 H3 标题结构**:`### [CARD] \`<id>\` · <metadata>` / `### [SESSION] \`<id>\` · <metadata>`,在同一层级出现但靠 `[TYPE]` 字面前缀分类 —— **视觉上像 Google 搜索的混合广告 + 蓝链,结构上保持 markdown 标题层次一致**。详见 [`../../cli/v3/search.md`](../../cli/v3/search.md)。

## 字段

### 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `search_id` | string | `sch_<ULID>`,审计 id |
| `query` | string | 回显请求 |
| `count` | integer | `results[]` 长度(可能 ≤ `top_k`,等于 `top_k` 说明被截断了) |
| `results` | object[] | 混合 card / session,按 `score` 降序排列 |

### `results[]` 共有字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `"card"` 或 `"session"`,**discriminator** |
| `rank` | integer | 1-based,对齐数组位置 |
| `score` | float | **final score**(`ranking_formula` 跑完);跨 type 直接可比 |

### `type = "card"` 专属字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `card_id` | string | `card_<ULID>` 带前缀 |
| `insight` | string | card 的洞见**整段** —— 已对匹配关键词内联 `**keyword**` 高亮。FTS 命中在 `card.rounds[].text` 而**不在** `insight` 时 → 整段无高亮,但 card 仍返回(读者要看 round 原文走 `read`) |
| `stats` | Stats | 当前快照,见 [talk-card.md#Stats](talk-card.md#stats) |

**没有 `snippets`** —— `insight` 已经是蒸馏后的一句话,直出比再抽片段更清楚。

**没有 `reviews`** —— search 不展开 review 列表,走 `POST /v3/read` 看完整列表。

**没有 `source_cards`** —— 同理,走 `read`。

### `type = "session"` 专属字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | `sess_<...>` 带前缀 |
| `source` | string | 平台来源(`claude-code` / `codex`) |
| `hit_count` | integer | 本 session 里命中的 round **总数** |
| `hits_shown` | integer | `hits[]` 实际长度(≤ `hit_count`,默认上限 3) |
| `hits` | Hit[] | 命中 round 的窗结构,见下方 |

**没有 `tags`** / **没有 `links`** —— v3 无这两个概念。

### Hit(session 内一个命中 round 的窗)

| 字段 | 类型 | 说明 |
|---|---|---|
| `index` | integer | 命中 round 在 session 内的稳定编号 |
| `role` | string | `human` / `assistant` / `tool` / `system` |
| `text` | string | round 原文,含 `**keyword**` 高亮(只对命中关键词加;长 round 不截断) |
| `score` | float | 本 round 的 RRF 检索分(原始相关度,**跟外层 session-level `score` 不同尺度**) |
| `context_before` | object\|null | 前一条 round `{index, role, text}`;长内容截 200 字 + `...`;`null` 表示是 session 第一条 |
| `context_after` | object\|null | 后一条 round;`null` 表示是最后一条 |

#### 上下文窗规则

- **窗大小固定**:前 1 行 + 后 1 行
- 上下文行**不过滤 role** —— tool / system / sidechain 也照常出
- 上下文行可能也含 keyword:照常 `**...**` 高亮(意味着上下文本身也跨命中)
- 同一 session 里相邻 round 都命中:**生成两个独立 hit**,不去重 —— 窗会重叠但**保留独立性**

#### Hits 排序

`hits[]` 默认按 `hits[].score` **降序**(round 级 RRF 分)。**不**按 `index` 顺序 —— 人类读者要先看最相关的命中,顺序追溯走 `POST /v3/read`。

### Score 尺度对照

| 字段 | 含义 | 用途 |
|---|---|---|
| `results[].score` | final score(`ranking_formula` 跑完) | 跨 type 排序、可直接比 |
| `hits[].score` | round 级 RRF 相关度 | session 内部 hit 排序,**不要跟 final score 混比** |

## ranking_formula 怎么跨 type 工作

形式上还是同一个公式,对 card 和 session **都跑一次**:

- **`relevance`** 来源不同:
  - card:`max(FTS over insight, FTS over rounds, vector over insight)` 之类的混合
  - session:本 session 所有命中 round 的 RRF 分**按 hits 聚合**(默认 `1 - prod(1 - score_round_i)`,衰减聚合,多命中加分但有上限;backend 配置可改成 `max` / `mean` 等)
- **stats 类变量**(`review_up` 等)对 session **统一置 0**
- **`age_days`** 是各自的 `created_at` 距今天数

跨 type 可比性来自:**两类候选过同一公式**,session 的 stats 项天然为 0,所以"sessions 只靠 relevance 和 age 拼分,cards 还能加 stats"是公式涌现的偏序,不是硬编码。

## 高亮渲染

`**word**` 标记 keyword 命中。两种场景:

- **card `insight`**:整段返回,FTS5 在 `insight` 文本上标 keyword;查无匹配 → 整段无高亮(命中可能在 `rounds[].text` 里)
- **session `hits[].text`** / **`context_before/after.text`**:每条 round 原文返回,匹配 keyword 内联 `**...**`

session 的 hit `text` **不截断**;`context_before/after.text` 超 200 字按字符截到 200 + `...`。

## SearchLog(服务端审计)

每次 `POST /v3/search` 在服务端追加一行,**记录完整呈现给使用者的结果**(包含 `results[]` 全字段,session hits 含上下文窗)。事后审计能完整复原"当时看到了什么",即便 sync 给 session 追加了新 round、card 拿到新 review 也对得回。

```json
{
  "search_id": "sch_01K7XABCDEFGHIJK01234",
  "query": "LanceDB 选型",
  "where": "review_count = 0 AND read_count > 10",
  "top_k": 10,
  "created_at": "2026-04-20T14:30:00Z",
  "count": 4,
  "results": [
    /* 跟响应一字不差 */
  ]
}
```

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `search_id` | string | `sch_<ULID>`,唯一 |
| `query` | string | 检索文本(可空) |
| `where` | string \| null | DSL 串(无则 null) |
| `top_k` | integer | 本次请求的 top_k |
| `created_at` | string | ISO 8601 服务端时间 |
| `count` | integer | `results[]` 长度 |
| `results` | object[] | 完整结果快照,跟响应同结构 |

### 为什么存完整响应

- `insight`(card,带内联高亮)/ `hits[].text`(session)由 FTS 在检索时基于**当时的文档内容**生成。后续 session 追加 round / card 拿到新 review 时重算结果可能不一样 —— 存原件才能真正复原"当时呈现给用户的"
- `score` 依赖模型 / 向量库状态 / `ranking_formula` / `top_k`,事后无法保证复现
- `stats` 会随后续 review / read / recall 演化 —— 存快照才能看到"当时这张 card 在论坛里的位置"
- `hits[].context_before/after` 是当时 session 的临近 round —— 后续平台覆写也保住原貌

### 落库

- **SQLite `search_log` 表**:`results` 用 JSON 列存整个 blob
- **`~/.memory-talk/logs/search/<YYYY-MM-DD>.jsonl`**:按 UTC 日期切分,每行一个完整 SearchLog 对象

```sql
CREATE TABLE search_log (
  search_id    TEXT PRIMARY KEY,
  query        TEXT NOT NULL,
  where_dsl    TEXT,                  -- "where" 是 SQL 保留字
  top_k        INTEGER NOT NULL,
  created_at   TIMESTAMP NOT NULL,
  count        INTEGER NOT NULL,
  results_json TEXT NOT NULL          -- JSON blob,含完整 results[]
);

CREATE INDEX idx_search_log_created_at ON search_log(created_at);
```

### 老化

按 `settings.search.search_log_retention_days`:

- `0` = 永不老化(默认)
- `> 0` = `created_at` 早于 `now - retention_days` 的行在下次启动 / 定期扫描时清除(SQLite 行 + jsonl 文件按天粒度)

### 不参与读取校验

SearchLog 纯粹审计 / 分析:看这台机器最近查什么、复原"这次 search 的用户呈现"、统计 query 质量。**绝不**参与后续命令的"凭据是否还活着"校验 —— v3 没有 result_id / token 机制。

## 跟 v2 的差异

| | v2 | v3 |
|---|---|---|
| 响应结构 | `cards: {count, results}` + `sessions: {count, results}` 两支 | **单一** `results[]`,`type` 字段做 discriminator |
| 排序 | 两支独立 RRF;UI 拼接(card 先、session 后) | 统一 `ranking_formula` 算 final score 后**混合降序** |
| card 字段 | `summary` + `links` + `tags` + `snippets[]`(片段数组) | `insight`(整段直出 + 内联高亮)+ `stats`,**无独立 `snippets[]`**(无 links / tags) |
| session 字段 | `tags` + `links` + `snippets[]`(平铺) | `hit_count` + `hits_shown` + `hits[]`(窗结构);无 tags / links / 平铺 snippets |
| 召回粒度 | session 整体一行,snippets 平铺 | session 内 round 行级,**多命中聚合到 hits[]**,带前后一行上下文 |
| `top_k` 语义 | 每支 top_k(总 2×top_k) | **总** top_k(card + session 合计) |
| `score` 含义 | RRF 原始相关度 | `ranking_formula` 跑完的 final score;`hits[].score` 才是 round 级 RRF |
| `search_id` 角色 | 审计 + `from_search_id` 关联 | 仅审计(card 入参不再带 `from_search_id`) |

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
| `text` | string | round 的**显示预算摘要**(默认 ~100 字符,配 `settings.search.snippet_head_chars`)。详见 [#hit-text-snippet-规则](#hit-text-snippet-规则) |
| `score` | float | 本 round 的 RRF 检索分(原始相关度,**跟外层 session-level `score` 不同尺度**) |
| `context_before` | object\|null | 前一条 round `{index, role, text}`;长内容截 200 字 + `…`;`null` 表示是 session 第一条 |
| `context_after` | object\|null | 后一条 round;`null` 表示是最后一条 |

#### Hit text snippet 规则

为了防止大 round(几千字符的代码 / 工具输出)把客户端撑爆,`hits[].text` **不再返 round 原文**,而是一段预算 ~`settings.search.snippet_head_chars` 字符的摘要。两种模式由 round text 里**是否出现任一 query token**(jieba 分词后)决定 —— 与召回管线(FTS / 向量)无关:

| 场景 | text 形态 | 高亮 |
|---|---|---|
| round 含至少一个 query token(典型 FTS 命中,以及那些"语义召回但碰巧也有词命中"的) | **以最早命中位置为中心**,前后各取约 `head_chars/2` 字符;两端被截则加 `…` 前 / 后缀 | 命中的 token 仍按规则 `**…**` 包裹 |
| round 不含任何 query token(典型纯向量命中,语义近但没词面重叠) | round **头 `head_chars` 字符 + `…`**(若被截断) | 无(text 里本就没匹配项) |
| round 总长 ≤ `head_chars` | 整段原文 | 命中的 token 照常 `**…**` 包裹 |

`context_before` / `context_after` 不受这条规则影响,仍是相邻 round 的前 200 字 + `…`(纯向量命中也保留 context,只是 context 文本通常也没词面高亮)。

#### 上下文窗规则

- **窗大小固定**:前 1 行 + 后 1 行
- 上下文行**不过滤 role** —— tool / system / sidechain 也照常出
- 上下文行可能也含 keyword:照常 `**...**` 高亮(意味着上下文本身也跨命中)
- 同一 session 里相邻 round 都命中:**生成两个独立 hit**,不去重 —— 窗会重叠但**保留独立性**

#### Hits 排序

`hits[]` 默认按 `hits[].score` **降序**(round 级 RRF 分)。**不**按 `index` 顺序 —— 人类读者要先看最相关的命中,顺序追溯走 `POST /v3/read`。

`hits[].text` 是预算摘要(默认 ~100 字符),要看 round 原文也走 `POST /v3/read`。

### Score 尺度对照

| 字段 | 含义 | 用途 |
|---|---|---|
| `results[].score` | final score(`ranking_formula` 跑完) | 跨 type 排序、可直接比 |
| `hits[].score` | round 级 RRF 相关度 | session 内部 hit 排序,**不要跟 final score 混比** |

## 排序算法

`POST /v3/search` 的混合排序走五步,每步只解一件事,合起来产出 `results[]` 里的 `rank` / `score` 字段。

```
LanceDB hybrid 召回(per round / per card)
        │  返回 RRF 原始分(K=60)
        ▼
1. 按 session_id 分组,sort hits desc by score        (仅 session)
        │
        ▼
2. session relevance = max(hits[].score)                (仅 session)
        │
        ▼
3. 跑 ranking_formula → final_score                     (card / session 同一套)
        │
        ▼
4. card + session 合并,按 final_score desc 混排
        │
        ▼
5. cut to top_k;每个 session 展示前 hits_per_session 个 hit
   (hits_shown ≤ hit_count;超出的 hit 既不展示也不参与排序)
```

每个 round 的"原始分"是 LanceDB `RRFReranker(K=60)` 跑完的 hybrid score,典型范围 **`0.01 – 0.03`**;**它只看排名,不看绝对相似度**(详见 [#关于-rrf-分的一句忠告](#关于-rrf-分的一句忠告))。

### Step 1:hits 排序

同一 session 内的所有命中 round 按 `hits[].score` 降序排。`results[].hits_shown` 是渲染上限(代码里硬编码 3,见 [`memorytalk/service/search.py`](../../../memorytalk/service/search.py) `_HITS_PER_SESSION`)。

### Step 2:session relevance = max(hits)

仅 session 这一支跑这一步。card 的 relevance 直接来自 LanceDB cards 表的 RRF 分,无需聚合。

公式([`_aggregate_session_relevance`](../../../memorytalk/service/search.py)):

```
relevance = max(hits[].score)
```

**为什么是 max,不是 noisy-OR / sum**

历史上用过 noisy-OR(`1 - Π(1 - s_i)`),想用"多 hit 加分,但有 diminishing returns"的语义。这条契约只在 `s_i → 1` 时成立 —— RRF 输出尺度是 `0.01 – 0.03`(`K=60` 决定的上限 ≈ `2/61 ≈ 0.0328`),在这个尺度下泰勒展开后 noisy-OR **退化为求和**:

| 14 个 `0.012` 弱 hit | 1 个 `0.031` 强 hit |
|---|---|
| noisy-OR ≈ `0.155` | `0.031` |
| **多弱 hit 完胜强单 hit 5×** —— 跟 docstring 承诺的"never exceeds the strongest single hit by much"完全相反 | |

实际后果:**询问者自己的会话因为复读 query(用户问 + AI 转写 + 工具 stdout)轻松拿 10+ 弱 hit,把"真正一次精确提问"的别人会话挤到后面**(详见 [`../../report/2026-05-21-search-noisy-or-aggregation-bug.md`](../../report/2026-05-21-search-noisy-or-aggregation-bug.md))。换成 `max` 后,这类 echo 噪声直接被压制。

> 损失了什么?理论上"多 hit 表明话题深度"的信号。实务里几乎不成立 —— 真深度讨论的 session 一定有至少一个"集中讨论"的强 RRF round,max 仍能选中;**纯靠多次弱命中的 session 几乎都是 echo / 路过式提及 / 模板回显**,本来就不该排前。
>
> 想把多 hit 当独立排序信号 → 在 `ranking_formula` 里用 `hit_count` 变量(暂未暴露,后续再加)。**不要回头去聚合公式里夹带私货**。

> v2 是分两路(cards / sessions)独立 RRF,各自取 top_k,UI 拼接 —— **不做这一步聚合**。v3 把 sessions 也压成单值是为了跟 cards 进同一个 formula。

### Step 3:ranking_formula 评估

card 和 session **过同一公式**(`settings.search.ranking_formula`,默认见 [settings.md#ranking_formula](settings.md#ranking_formula)):

```
relevance + 0.1 * (review_up - review_down) + 0.02 * log(read_count + 1) - 0.005 * age_days
```

变量来源:

| 变量 | card | session |
|---|---|---|
| `relevance` | LanceDB cards 表 RRF 分 | step 2 的 `max(hits[].score)` |
| `review_up` / `review_down` / `review_neutral` / `review_count` / `read_count` / `recall_count` | `card.stats.*` | **统一置 0** |
| `age_days` | 距 `card.created_at` 天数 | 距 `session.created_at` 天数 |

完整变量 / 函数白名单见 [settings.md#ranking_formula](settings.md#ranking_formula)。

### Step 4:跨 type 混排

`merged = card_candidates + session_candidates`,**按 `final_score` 降序**统一排。

跨 type 可比性来自"**两类候选过同一公式**":

- **card** 四项全启用,有 stats bonus —— 一张被 review_up 几次 + 偶尔被 read 的 card,final_score 容易 `0.5+`
- **session** stats vars 全 0,实际只剩 `relevance - 0.005 * age_days`,而 relevance = 最强 hit 的 RRF 分,典型 `0.03` 上下

所以**默认配置下 card 天然占便宜**。这是公式涌现的偏序,不是硬编码"卡先于会话"。

想让 session 更突出 → 改 `settings.search.ranking_formula`,比如 `2 * relevance + ...` 或者去掉 stats 项。**所有动力学杠杆都在 settings 这一个公式**,没散落在 service 代码里。

### Step 5:top_k 截断 + hits_shown 展示

`merged[:top_k]` 截断,得到最终 `results[]`。session 内部再切前 `_HITS_PER_SESSION`(目前硬编码 3)个 hit 进 `hits[]`。

**hits_shown 上限不影响排序** —— session relevance 只看 step 1 排序后的 `hits[0].score`,而 `hits[0]` 必定在展示的前 3 个里,所以"截掉的 hit"对排序没贡献。`hit_count` 字段告诉读者本 session 实际有多少命中(可能远多于 `hits_shown`),纯展示用。

### 关于 RRF 分的一句忠告

`hits[].score`(LanceDB RRF 原始分)**只看排名,不看绝对相似度**:

- 一个 round 即便余弦相似度只有 `0.3`(语义实际很弱),只要它进了向量 top-K,RRF 照样给分
- 反过来,FTS 完全没命中 query token 的 round,向量 rank 高时 RRF 也给高分 —— **这就是"语义召回但词面无关"的来源**,也是"有些 hit 看着不那么贴"的根因

RRF 不暴露"FTS / vector / both" 来源(`RRFReranker` 内部合并后扔了)。要拿到这个信号,SearchService 得自己分两路独立查 + 自融合,目前没做。

#### 为什么不用 LinearCombinationReranker

直觉上 `LinearCombination` 用真实 BM25 + 向量分,应该比 RRF 的纯排名更准。**实际上 `lancedb==0.30.x` 的实现是反向的**:

```python
combined = 1 - (0.7 * vec_sim + 0.3 * bm25_raw)
```

`bm25_raw` 无界(强匹配 ~30+),`vec_sim` 在 `[0, 1]` —— BM25 占主导且**越高分越被打低**,完美 text 匹配的 round 在 min-max 归一化后接近 0,被"两路都弱但 fill 撑起来"的噪声压到 #2000 外。Lance 上游 docstring 自己标了 `TODO: pretty confusing as we invert scores`。

2026-05-23 切过去又当天回滚 —— 详见 [`../../report/2026-05-23-search-linear-combination-regression.md`](../../report/2026-05-23-search-linear-combination-regression.md)。**不要再切**,除非:(a) Lance 上游修了 inversion + 加了归一化,或 (b) 落地一个 search-quality 回归测试(固定 query + 固定 corpus,断言"完美匹配 round 必在 top-k")。

### 实务直觉

排序在意料之外时,按这个顺序自查:

1. **session 排得低** → 它 stats 全 0 在跟有 stats bonus 的 card 比,改公式
2. **session A 顶部 hit 比 B 强但 A 排在 B 后** → A 更旧,被 `-0.005 * age_days` 拉下去了;hit 数量本身不影响排序
3. **某 hit 看着"不那么贴"** → 多半是纯向量召回拿了 RRF 分,词面零命中。看 hit text 里是否含 query token
4. **整体分都偏低** → query 在 LanceDB 召回阶段就稀疏,扩 oversample(`_CARD_OVERSAMPLE` / `_ROUNDS_OVERSAMPLE`)或换公式让 stats 权重盖过 relevance

## 高亮渲染

`**word**` 标记 keyword 命中。三种场景:

- **card `insight`**:整段返回,FTS5 在 `insight` 文本上标 keyword;查无匹配 → 整段无高亮(命中可能在 `rounds[].text` 里)
- **session `hits[].text`**:按 [#hit-text-snippet-规则](#hit-text-snippet-规则)裁成预算摘要;有词面命中走 keyword window,纯向量命中走 head 预览
- **`context_before/after.text`**:相邻 round 截前 200 字 + `…`,匹配 keyword 内联 `**…**`(向量命中的 context 通常无词面命中,因此无高亮)

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

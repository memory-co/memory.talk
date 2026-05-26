# Talk-Card

v3 的核心数据结构 —— 从对话中提炼出的记忆单元。**append-only**:payload 创建即冻结;stats 是 runtime 状态由后端实时维护。论坛动力学语义见 [`../../cli/v3/README.md`](../../cli/v3/README.md)。

## Schema

```json
{
  "card_id": "card_01jz8k2m",
  "insight": "选定 LanceDB 做向量存储,主要是零依赖、嵌入式架构",
  "rounds": [
    {"role": "human", "text": "向量库选型,ChromaDB 和 LanceDB 哪个好?", "session_id": "sess_f7a3e1", "index": 11},
    {"role": "assistant", "text": "推荐 LanceDB:零依赖、本地文件存储、适合嵌入式部署。", "thinking": "关键考量是部署形态——Skill 嵌入式场景不能要求用户启动额外服务", "session_id": "sess_f7a3e1", "index": 12}
  ],
  "source_cards": [
    {"card_id": "card_01jzaaaa", "relation": "supersedes"},
    {"card_id": "card_01jzbbbb", "relation": "derives_from"}
  ],
  "tags": {
    "project": "billing",
    "status": "verified"
  },
  "stats": {
    "review_up": 7,
    "review_down": 3,
    "review_neutral": 2,
    "review_count": 12,
    "read_count": 42,
    "recall_count": 18
  },
  "reviews": [
    {"review_id": "review_01jzr5kq", "session_id": "sess_def456", "indexes": "20-25", "score": 1, "comment": "...", "created_at": "2026-05-01T09:14:22Z"}
  ],
  "created_at": "2026-04-10T14:30:00Z"
}
```

> 上面是 `POST /v3/read` 响应里**合并后**的视图。底层落盘 / SQLite 是分开存的:`card.json` 只存 immutable payload;stats / reviews 在 SQLite。详见 [#存储](#存储)。

## 字段

### Immutable payload

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 自动 | `card_<ULID>`,不提供则自动生成 |
| `insight` | string | 是 | 一句话认知洞见,也是 embedding 锚点 |
| `rounds` | Round[] | 是 | 展开后的对话轮次(见下方 Round 结构),每条带 `session_id` + `index` 指回源 session。可为空数组(纯 source_cards 派生的高阶 card) |
| `source_cards` | SourceCard[] | 否 | card 间关联,创建时确定,**不可改**(见下方 SourceCard 结构);空数组 / 不传等价 |
| `created_at` | string | 自动 | ISO 8601 |

### User-side metadata(可改,但跟 immutable payload 解耦)

| 字段 | 类型 | 说明 |
|---|---|---|
| `tags` | object | 0.8.x 新字段。string→string 字典,user-side 手动打的轻量组织标签。**不参与论坛动力学**(不进 sort / 不算 stats / 不进 vector index),纯查询 / 归类用。约束:key 匹配 `^[a-zA-Z][a-zA-Z0-9_.-]*$`,value ≤ 200 char,单 card key 数 ≤ 50。详见 [`../../cli/v3/card.md#card-tag`](../../cli/v3/card.md#card-tag) |

> tag 跟 immutable payload 解耦:**改 tag 不破坏 append-only 不变性**。append-only 约束的是 `insight` / `rounds` / `source_cards` —— 它们承载论坛主张和 lineage,改了就把"老观点复活"和"fork 谁取代谁"的判断基础挪走;tag 不在这个语义层,它只是给已存在的 card 贴归类标签。

### Runtime state(不在 payload 里,由后端实时维护)

| 字段 | 类型 | 说明 |
|---|---|---|
| `stats` | Stats | 6 个计数器,见 [#Stats](#stats) |
| `reviews` | Review[] | 本卡所有 review,按 `created_at` 倒序 |

## Round(Talk-Card 中)

由 `POST /v3/cards` 入参里 `rounds` 字段的 `{session_id, indexes}` 展开而来,对齐 `session.rounds[].index`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `role` | string | `human` / `assistant` |
| `text` | string | 从 session 对应 round 摘出来的文本 |
| `thinking` | string\|null | 可选,关键思考思路 |
| `session_id` | string | 该 round 来自哪个 session |
| `index` | integer | 该 round 在源 session 里的 `index` |

跟 Session 中的 Round 不同:**没有** `round_id` / `parent_id` / `timestamp` / `content` block 等原始结构。要追溯原始 round,用 `session_id` + `index` 直接定位源 session 的 `rounds[index]`。这是记忆,不是录像。

`session_id` / `index` 只是元数据,**不进向量检索** —— 向量侧只 embed `insight`,数字 id 在语义检索里没意义。

完整 Session Round 结构见 [session.md](session.md)。

## SourceCard

card 之间的关联,创建时确定,**不可改**。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 是 | 被引用 card 的 id,必须是 `card_<...>` |
| `relation` | string | 是 | 关系类型 |

`relation` 取值:

| 值 | 语义 |
|---|---|
| `derives_from` | 本卡基于该 card 蒸馏 / 综述(高阶 card 引用低阶 card 的典型形态) |
| `supersedes` | 本卡**反驳并替代**该 card(fork 语义)。老 card 不被删,后续是否真被取代由动力学说了算 —— 没有"立即把老 card 打成 dormant"这种硬切换 |

后续可能扩展 `cites` / `merges` 等;后端遇未识别 `relation` 返回 400。

**lineage DAG 不变性**:card 创建后不可改 + `source_cards` 只能引用**创建时已存在**的 card,物理时序就保证 lineage 图是有向无环图。后端不做环检测。

## Stats

后端实时维护的计数器,**真讨论 vs 路过分开**(对应论坛动力学 §5):

| 字段 | 含义 | 累加时机 |
|---|---|---|
| `review_up` | `+1` review 数 | `POST /v3/reviews` 且 `score=1` |
| `review_down` | `-1` review 数 | `POST /v3/reviews` 且 `score=-1` |
| `review_neutral` | `0` review 数(中立) | `POST /v3/reviews` 且 `score=0` |
| `review_count` | review 总数(= up + down + neutral) | 每次 `POST /v3/reviews` |
| `read_count` | `POST /v3/read` 命中本卡的次数 | 每次 read card |
| `recall_count` | `POST /v3/recall` 返回过本卡的次数 | 每次新返回(被 skipped_already_recalled 跳掉的不计) |

**沉浮公式**(默认配在 `settings.search.ranking_formula`)消费这些字段:

```
relevance + 0.1 * (review_up - review_down) + 0.02 * log(read_count + 1) - 0.005 * age_days
```

`review_neutral` 默认权重 0,但仍单独存,允许用户改公式时调用(讨论广度信号)。

完整公式 / 变量 / DSL 引用见 [`../../cli/v3/search.md`](../../cli/v3/search.md#排序)。

## 存储

### Immutable payload(文件)

```
cards/{card_id[5:7]}/{card_id}/
├── card.json           # immutable payload + created_at
├── events.jsonl        # created / reviewed / read_at / recalled_at
└── reviews.jsonl       # 本卡所有 review 的镜像(audit / portability)
```

`{card_id[5:7]}` 是 ULID 部分的前 2 个字符(跳过 `card_` 前缀)。

### Runtime state(SQLite)

```sql
-- 卡的 stats(行级 upsert)
CREATE TABLE card_stats (
  card_id        TEXT PRIMARY KEY,
  review_up      INTEGER NOT NULL DEFAULT 0,
  review_down    INTEGER NOT NULL DEFAULT 0,
  review_neutral INTEGER NOT NULL DEFAULT 0,
  review_count   INTEGER NOT NULL DEFAULT 0,
  read_count     INTEGER NOT NULL DEFAULT 0,
  recall_count   INTEGER NOT NULL DEFAULT 0,
  updated_at     TIMESTAMP NOT NULL
);

-- card 索引(查询用)
CREATE TABLE cards (
  card_id    TEXT PRIMARY KEY,
  insight    TEXT NOT NULL,
  tags       TEXT NOT NULL DEFAULT '{}',  -- 0.8.x 新增,user-level kv 标签
  created_at TIMESTAMP NOT NULL
);

-- source_cards 关系(查询用)
CREATE TABLE card_source_cards (
  card_id         TEXT NOT NULL,    -- 本卡
  source_card_id  TEXT NOT NULL,    -- 被引用的 card
  relation        TEXT NOT NULL,    -- derives_from / supersedes / ...
  seq             INTEGER NOT NULL, -- 在 source_cards[] 里的位置
  PRIMARY KEY (card_id, seq)
);
```

向量侧只 embed `insight`,索引在 `vectors/` 目录(LanceDB)。

## 跟 v2 的差异

| | v2 | v3 |
|---|---|---|
| 字段名 | `summary` | `insight` |
| 关联载体 | `links[]`(独立 link 对象 + TTL) | `source_cards[]`(card 字段 + 不可改) |
| 状态 | `ttl` + view 续命 | `stats` + 沉浮公式 |
| 创建后改 | `links` 可加可改 ttl | 全 immutable,只能新建 |
| tag | 单独 sqlite 表(字符串列表),自动从 sync / explore 注入,view card 时 join | **0.8.x 加回**,但形态变了:string→string 字典存在 `cards.tags` 列里,只 user-side 手动 PATCH,不参与论坛动力学。详见 [`../../cli/v3/card.md`](../../cli/v3/card.md) |
| 写入入参 | `summary` + `rounds` + (没 links,默认自动生成) | `insight` + `rounds` + `source_cards`(可选) |

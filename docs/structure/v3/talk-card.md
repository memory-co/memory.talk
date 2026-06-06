# Talk-Card

v3 的核心数据结构 —— 从对话中提炼出的记忆单元。**append-only**:payload 创建即冻结;stats 是 runtime 状态由后端实时维护。

论坛动力学语义见 [`../../works/v3/forum-dynamics.md`](../../works/v3/forum-dynamics.md)。
创建/删除流程见 [`../../works/v3/card-creation-flow.md`](../../works/v3/card-creation-flow.md) / [`../../works/v3/card-deletion-flow.md`](../../works/v3/card-deletion-flow.md)。

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

上面是 `POST /v3/read` 响应里**合并后**的视图。底层 `card.json` 只存 immutable payload;stats / reviews 在 SQLite,详见 [#存储](#存储)。

## 字段

### Immutable payload

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 自动 | `card_<ULID>`,不提供则自动生成 |
| `insight` | string | 是 | 一句话认知洞见,也是 embedding 锚点 |
| `rounds` | Round[] | 是 | 展开后的对话轮次(见 [#Round](#round-talk-card-中)),每条带 `session_id` + `index` 指回源 session。可为空数组 |
| `source_cards` | SourceCard[] | 否 | card 间关联,创建时确定不可改 |
| `created_at` | string | 自动 | ISO 8601 |

### User-side metadata(可改,但跟 immutable payload 解耦)

| 字段 | 类型 | 说明 |
|---|---|---|
| `tags` | object | string→string 字典,用户手动打的轻量标签。约束:key 匹配 `^[a-zA-Z][a-zA-Z0-9_.-]*$`,value ≤ 200 char,单 card key 数 ≤ 50。详见 [`../../cli/v3/card.md`](../../cli/v3/card.md) |

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

跟 Session 中的 Round 不同:没有 `round_id` / `parent_id` / `timestamp` / `content` block。要追溯原始 round 用 `session_id` + `index` 定位 session 的 `rounds[index]`。

完整 Session Round 结构见 [session.md](session.md)。

## SourceCard

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 是 | 被引用 card 的 id,必须 `card_<...>` |
| `relation` | string | 是 | 关系类型 |

`relation` 取值:

| 值 | 语义 |
|---|---|
| `derives_from` | 本卡基于该 card 蒸馏 / 综述 |
| `supersedes` | 本卡反驳并替代该 card(fork 语义) |

后端遇未识别 `relation` 返回 400。lineage DAG 由"创建时必须存在"+ append-only 联合保证,见 [`../../works/v3/card-creation-flow.md`](../../works/v3/card-creation-flow.md)。

## Stats

| 字段 | 含义 |
|---|---|
| `review_up` | `score=+1` review 数 |
| `review_down` | `score=-1` review 数 |
| `review_neutral` | `score=0` review 数 |
| `review_count` | review 总数(= up + down + neutral) |
| `read_count` | `POST /v3/read` 命中本卡的次数 |
| `recall_count` | `POST /v3/recall` 返回过本卡的次数(0.9.0 起 derived,见 [forum-dynamics.md](../../works/v3/forum-dynamics.md)) |

stats 的累加细节 + 公式怎么消费这些字段 见 [`../../works/v3/forum-dynamics.md`](../../works/v3/forum-dynamics.md) 和 [`../../works/v3/search-ranking.md`](../../works/v3/search-ranking.md)。

## 存储

### Immutable payload(文件)

```
cards/{card_id[5:7]}/{card_id}/
├── card.json           # immutable payload + created_at
├── events.jsonl        # created / reviewed / read_at
├── reviews.jsonl       # 本卡所有 review 的镜像(audit / portability)
└── tags.json           # user-side tags sidecar(0.8.x)
```

`{card_id[5:7]}` 是 ULID 部分的前 2 个字符(跳过 `card_` 前缀)。

### Runtime state(SQLite)

```sql
-- 卡的 stats(0.9.0 起 recall_count 列被 drop,改 derived)
CREATE TABLE card_stats (
  card_id        TEXT PRIMARY KEY,
  review_up      INTEGER NOT NULL DEFAULT 0,
  review_down    INTEGER NOT NULL DEFAULT 0,
  review_neutral INTEGER NOT NULL DEFAULT 0,
  review_count   INTEGER NOT NULL DEFAULT 0,
  read_count     INTEGER NOT NULL DEFAULT 0,
  updated_at     TIMESTAMP NOT NULL,
  FOREIGN KEY (card_id) REFERENCES cards(card_id)
);

-- card 索引(查询用)
CREATE TABLE cards (
  card_id    TEXT PRIMARY KEY,
  insight    TEXT NOT NULL,
  tags       TEXT NOT NULL DEFAULT '{}',
  created_at TIMESTAMP NOT NULL
);

-- source_cards 关系(查询用)
CREATE TABLE card_source_cards (
  card_id         TEXT NOT NULL,
  source_card_id  TEXT NOT NULL,
  relation        TEXT NOT NULL,
  seq             INTEGER NOT NULL,
  PRIMARY KEY (card_id, seq)
);
CREATE INDEX idx_csc_source ON card_source_cards(source_card_id);
```

向量侧只 embed `insight`,索引在 `vectors/` 目录(LanceDB)。

存储分层(file canonical + SQLite index)总体模式见 [`../../works/v3/file-canonical-pattern.md`](../../works/v3/file-canonical-pattern.md)。

## 跟 v2 的差异

| | v2 | v3 |
|---|---|---|
| 字段名 | `summary` | `insight` |
| 关联载体 | `links[]`(独立 link 对象 + TTL) | `source_cards[]`(card 字段 + 不可改) |
| 状态 | `ttl` + view 续命 | `stats` + 沉浮公式 |
| 创建后改 | `links` 可加可改 ttl | 全 immutable,只能新建 |
| tag | 单独 sqlite 表(字符串列表) | `cards.tags` 列(string→string 字典),不参与论坛动力学 |

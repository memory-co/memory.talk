# Filesystem (v4)

v4 卡子系统在 data root(**固定** `~/.memory.talk/`)下产生的文件 / 目录 / SQLite 表 / LanceDB collection —— 这一页只回答「v4 的卡到底放在磁盘哪、双写关系是什么」。字段语义见对应对象 md。

> v4 **只新增 / 重写卡子系统这一层**。`sessions/` 镜像、`sync.db`、`logs/`、顶层 `settings.json` / `server.pid` 等沿用 v3,不在这里复制,见 [`../v3/filesystem.md`](../v3/filesystem.md)。

## 全景(卡子系统部分)

```
~/.memory.talk/
├── memory.db                              # SQLite 主库 —— 查询主路径
├── cards/<bucket>/<card_id>/              # bucket = card_id 去 card_ 前缀后前 2 字符
│   ├── card.json                          # canonical:issue + created_at(问题不可变,写一次)
│   ├── positions/
│   │   └── <pid>.json                     # canonical:claim + created_at(答案核不可变,写一次)
│   └── events.jsonl                       # 卡生命周期事件(created / position_added / reviewed / linked / ...)
├── insights/<bucket>/<insight_id>/        # v3 card 改名而来,只读(payload 保留;见 v3 talk-card.md)
│   └── ...
├── vectors/                               # LanceDB 数据目录
│   ├── cards.lance/                       # 表:cards(embed issue)—— 问题级检索
│   ├── positions.lance/                   # 表:positions(embed claim)—— 答案级检索
│   ├── insights.lance/                    # 表:insights(= v3 cards collection 改名 copy,只读可搜)
│   └── rounds.lance/                      # 表:rounds(session round,沿用 v3)
└── sessions/<source>/<id[0:2]>/<sid>/     # 沿用 v3;逐 round mark 落在这里(见下)
    ├── meta.json
    ├── rounds.jsonl
    ├── marks/                             # 逐 round mark:一条一个 m<n>.yaml(见 session-mark.md)
    │   ├── m1.yaml                        #   last_index + description + round_index + mark + questions[]
    │   └── m2.yaml                        #   questions[] = card_sessions 的 canonical
    └── events.jsonl
```

设计原则:**SQLite 是查询主路径**(计数 / 现算排序 / 关系 join / DSL);**文件罐是 canonical**(可移植 / 审计,db 丢能重建);**LanceDB 是检索召回的唯一来源**(embed `cards.issue` + `positions.claim`)。

## cards 镜像(每卡一目录)

布局 `cards/<bucket>/<card_id>/`,`<bucket>` = `card_id` ULID 部分前 2 字符(代码 `card_id[5:7]`,跳过固定 `card_` 前缀)。

| 文件 | 内容 | 写入时机 |
|---|---|---|
| `card.json` | `issue` + `created_at`(问题不可变核) | 卡创建时,**写一次,不再改** |
| `positions/<pid>.json` | `claim` + `created_at`(答案不可变核) | 每加一个 Position 写一份,**写一次,不再改** |
| `events.jsonl` | 卡 / Position 生命周期事件 | 各路径触发时追加 |

**events.jsonl 事件(建议集,落地时以代码为准)**:

| event | 触发点 | 关键字段 |
|---|---|---|
| `created` | 卡创建 | `issue_preview` |
| `position_added` | 卡下新增一个 Position(miss 首答 / 冲突竞争答) | `position_id`, `forked_from_position_id?` |
| `reviewed` | 某 Position 收到一条 review | `review_id`, `position_id`, `argument`, `session_id`, `indexes` |
| `card_linked` | 本卡被另一张卡在 `card_links` 里引用 | `from_card`, `type` |
| `session_cited` | 一条 `card_sessions` 关联了本卡 | `session_id`, `mark`, `position_id?` |
| `vector_index_failed` | LanceDB 写 issue / claim 向量失败(best-effort) | `error` |

`scope` / `forked_from_position_id` 改动若开放(本稿 Position append-only,默认不改),也走 events。`credence` 不是字段,无事件。

## memory.db(SQLite)—— 卡子系统的表

DDL 详见各对象 md 的「存储」小节。**全部无 FOREIGN KEY**(SQLite 是文件罐的派生索引,容忍悬空)。

| 表 | 粒度 | 用途 | 详见 |
|---|---|---|---|
| `cards` | 一行一卡 | `issue` + `created_at` + `position_count` / `link_count`(冗余) | [card.md](card.md) |
| `positions` | 一行一答案 | `claim` + `up/down/neutral_count` + `review_count`(冗余) + `scope` + `forked_from_position_id` | [card.md](card.md) |
| `reviews` | 一行一表态 | `position_id` / `card_id` / `session_id` / `indexes` / `argument` / `comment` | [review.md](review.md) |
| `card_links` | (card_id, type, target_id) | card↔card IBIS 边(+ `target_type` 派生列) | [card-link.md](card-link.md) |
| `card_sessions` | (card_id, session_id, mark, position_id) | card↔session 出处(`mark` = 哪条 mark) | [card-session.md](card-session.md) |
| `session_marks` | (session_id, mark) | mark 元信息(round_index / last_index;撑乐观锁 + 寻址) | [session-mark.md](session-mark.md) |

索引:`idx_pos_card`(positions.card_id)、`idx_reviews_position`(position_id, created_at DESC)、`idx_reviews_card`(card_id)、`idx_card_sessions_session`(session_id)、`idx_card_sessions_mark`(session_id, mark)、`idx_session_marks_session`(session_id)。

> **credence 不在任何表**:它是 `up_count`/`down_count` 的现算函数,排序时算,不落列(见 [card.md](card.md))。「当下答案」(accepted)、「相不相关」(salience)同样不存 —— 召回时现算。

## vectors/(LanceDB)

`vectors/` 是 LanceDB data dir,应用层只关心 collection 的逻辑结构:

| collection | 行 | 字段 | 用途 |
|---|---|---|---|
| `cards` | 一行一卡 | `card_id` / `text`(= `issue` 分词)/ `vector` | **问题级检索**(写路径 question 撞它判 miss/hit;读路径也撞) |
| `positions` | 一行一答案 | `position_id` / `card_id` / `text`(= `claim` 分词)/ `vector` | **答案级检索**(召回撞答案文本,争议卡里贴 context 的那侧排上来) |
| `insights` | 一行一 insight | `insight_id` / `text` / `vector` | v3 `cards` collection 原样 copy 改名,insight 仍可搜(只读) |
| `rounds` | 一行一 session round | `session_id` / `idx` / `text` / `vector` | 沿用 v3 |

**embed 两处**:`cards.issue`(问题 = 答案们的适用条件)+ `positions.claim`(答案文本)。召回撞两库——问题相关 + 答案相关一起决定召回哪些 Position;**争议卡靠 claim↔context 相似度自然选边,不需要额外争议判定**。

## 逐 round mark(card_sessions 的 canonical)

v4 写路径前端 = **逐 round mark(以写代读)**,落在 session 目录的 `marks/` —— **一条 mark 一个 `m<n>.yaml`**(`last_index` 乐观锁 + `description` + `round_index` + `mark` 正文 + 解析出的 `questions[]`)。mark **不是一等 id**,是 session 附属,寻址 `<session_id>#m<n>`。`questions[]` 是 card↔session 关联的 **canonical**;SQLite `card_sessions`(card→card 的出处边)+ `session_marks`(mark 元信息)都是它的派生索引。详见 [session-mark.md](session-mark.md)、[`../../works/v4/session-mark.md`](../../works/v4/session-mark.md) 与 [card-session.md](card-session.md)。

## 一张图看清「每类信息落在哪几处」

| 类别 | SQLite | 文件 | LanceDB |
|---|---|---|---|
| card 不可变核(issue) | `cards` | `card.json` | — |
| card embedding(issue) | — | — | `cards` collection |
| position embedding(claim) | — | — | `positions` collection |
| position 不可变核(claim) | `positions`(照抄 claim) | `positions/<pid>.json` | — |
| card 冗余计数(position_count/link_count) | `cards` | — | — |
| position 顶踩计数(up/down/neutral)+ review_count(冗余) | `positions` | — | — |
| position 治理(scope / forked_from) | `positions` | — | — |
| credence / 当下答案 / 相不相关 | **不存(现算)** | — | — |
| review payload | `reviews` | `reviews.jsonl`(卡目录下,沿用 v3) | — |
| card↔card 边 | `card_links` | (待定,见 §12) | — |
| card↔session 出处 | `card_sessions`(派生) | `marks/m<n>.yaml` 的 `questions[]`(canonical) | — |
| mark 元信息(round / last_index) | `session_marks`(派生) | `marks/m<n>.yaml` | — |
| 卡 / position 事件 | — | `events.jsonl`(卡目录下) | — |
| insight(v3 遗产) | `insights` 系列表 | `insights/<bucket>/...` | `insights` collection |

## 跟 v3 filesystem 的差异

| | v3 | v4 |
|---|---|---|
| 卡目录 | `cards/<bucket>/<card_id>/card.json`(整卡一个 payload) | 同前缀,但 `card.json`(问题)+ `positions/<pid>.json`(每答案一份) |
| 卡子系统 SQLite 表 | `cards` / `card_stats` / `card_source_cards` / `reviews` | `cards` / `positions` / `reviews` / `card_links` / `card_sessions` / `session_marks` |
| engagement 计数 | `card_stats.read_count` / `recall_count` 落库 | 不存(召回时现算) |
| 质量分 | 沉浮公式吃多列 | credence 现算 = f(up, down),不落列 |
| 出处 | `rounds[].session_id` 内联 | `card_sessions` 表 + mark `questions[]`(`marks/m<n>.yaml`) |
| LanceDB | `cards`(embed insight)+ `rounds` | `cards`(embed issue)+ `positions`(embed claim)+ `insights`(v3 遗产)+ `rounds` |
| FOREIGN KEY | `card_stats` 有 FK | **全无 FK**(贯彻派生索引立场) |

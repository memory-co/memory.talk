# Filesystem (v4)

v4 卡子系统在 data root(**固定** `~/.memory.talk/`)下产生的文件 / 目录 / SQLite 表 / LanceDB collection —— 这一页只回答「v4 的卡到底放在磁盘哪、双写关系是什么」。字段语义见对应对象 md。

> v4 **只新增 / 重写卡子系统这一层**。`sessions/` 镜像、`sync.db`、`logs/`、顶层 `settings.json` / `server.pid` 等的磁盘布局**沿用 v3**;为了让本页自洽,这套沿用层在末尾 [#沿用层session--sync--logs--settings](#沿用层session--sync--logs--settings) 里完整列出。

## 全景(卡子系统部分)

```
~/.memory.talk/
├── memory.db                              # SQLite 主库 —— 查询主路径
├── cards/<bucket>/<card_id>/              # bucket = card_id 去 card_ 前缀后前 2 字符
│   ├── card.json                          # canonical:issue + created_at(问题不可变,写一次)
│   ├── positions/
│   │   └── p<n>.json                      # canonical:claim + created_at(答案核不可变,写一次),文件名 = 卡内序号 p<n>
│   ├── links/
│   │   └── l<n>.json                      # canonical:type + target_id + claim + created_at(边核不可变,写一次),文件名 = l<n>
│   └── events.jsonl                       # 卡生命周期事件(created / position_added / reviewed / linked / ...)
├── insights/<bucket>/<insight_id>/        # v3 card 改名而来,只读(payload 保留;见 v3 talk-card.md)
│   └── ...
├── vectors/                               # LanceDB 数据目录
│   ├── cards.lance/                       # 表:cards(embed issue)—— 问题级检索
│   ├── positions.lance/                   # 表:positions(embed claim)—— 答案级检索
│   ├── insights.lance/                    # 表:insights(= v3 cards collection 改名 copy,只读可搜)
│   └── rounds.lance/                      # 表:rounds(session round,沿用 v3)
└── sessions/<source>/<id[0:2]>/<sid>/     # 沿用 v3;session mark 落在这里(见下)
    ├── meta.json
    ├── rounds.jsonl
    ├── marks/                             # session mark:一条一个 m<n>.yaml(见 session-mark.md)
    │   ├── m1.yaml                        #   last_index + description + mark + issues[]
    │   └── m2.yaml                        #   issues[] = card_sessions 的 canonical
    └── events.jsonl
```

设计原则:**SQLite 是查询主路径**(计数 / 现算排序 / 关系 join / DSL);**文件罐是 canonical**(可移植 / 审计,db 丢能重建);**LanceDB 是检索召回的唯一来源**(embed `cards.issue` + `positions.claim`)。

## cards 镜像(每卡一目录)

布局 `cards/<bucket>/<card_id>/`,`<bucket>` = `card_id` ULID 部分前 2 字符(代码 `card_id[5:7]`,跳过固定 `card_` 前缀)。

| 文件 | 内容 | 写入时机 |
|---|---|---|
| `card.json` | `issue` + `created_at`(问题不可变核) | 卡创建时,**写一次,不再改** |
| `positions/p<n>.json` | `claim` + `created_at`(答案不可变核) | 每加一个 Position 写一份(文件名 = 卡内序号 `p<n>`),**写一次,不再改** |
| `links/l<n>.json` | `type` + `target_id` + `claim` + `created_at`(边不可变核) | 每建一条 CardLink 写一份(文件名 = 卡内序号 `l<n>`),**写一次,不再改** |
| `events.jsonl` | 卡 / Position / Link 生命周期事件 | 各路径触发时追加 |

**events.jsonl 事件(建议集,落地时以代码为准)**:

| event | 触发点 | 关键字段 |
|---|---|---|
| `created` | 卡创建 | `issue_preview` |
| `position_added` | 卡下新增一个 Position(miss 首答 / 冲突竞争答) | `position`(p<n>), `forked_from?` |
| `reviewed` | 某 Position / Link 收到一条 review | `review_id`, `target`(p<n> / l<n>), `target_kind`, `argument`, `session_id`, `indexes` |
| `link_added` | 本卡建了一条出边(CardLink) | `link`(l<n>), `type`, `target_id`, `target_type` |
| `card_linked` | 本卡被另一张卡在 `card_links` 里引用 | `from_card`, `type` |
| `session_cited` | 一条 `card_sessions` 关联了本卡(经 mark) | `session_id`, `mark`, `indexes` |
| `vector_index_failed` | LanceDB 写 issue / claim 向量失败(best-effort) | `error` |

`scope` / `forked_from` 改动若开放(本稿 Position append-only,默认不改),也走 events。`credence` 不是字段,无事件。

## memory.db(SQLite)—— 卡子系统的表

DDL 详见各对象 md 的「存储」小节。**全部无 FOREIGN KEY**(SQLite 是文件罐的派生索引,容忍悬空)。

| 表 | 粒度 | 用途 | 详见 |
|---|---|---|---|
| `cards` | 一行一卡 | `issue` + `created_at` + `position_count` / `link_count`(冗余) | [card.md](card.md) |
| `positions` | (card_id, position) | `claim` + `up/down/neutral_count` + `review_count`(冗余) + `scope` + `forked_from` | [card.md](card.md) |
| `reviews` | 一行一表态 | `card_id` / `target`(p<n> / l<n>) / `target_kind`(position/link) / `session_id` / `indexes` / `argument` / `comment` | [review.md](review.md) |
| `card_links` | (card_id, link) | card↔card IBIS 边,**受治理**:`link`(l<n>) + `type` + `target_id` + `target_type`(派生)+ `claim` + `up/down/neutral_count` + `review_count`(冗余);UNIQUE `(card_id, type, target_id)` 不重边 | [card-link.md](card-link.md) |
| `card_sessions` | (card_id, session_id, mark) | **card→session** 出处(经 mark;记 grounding `indexes`;同一对可多条) | [card-session.md](card-session.md) |
| `position_sessions` | (card_id, position, session_id, mark) | **position→session** 出处(答案来自哪几轮 `indexes`;**mark 可选**) | [position-session.md](position-session.md) |
| `link_sessions` | (card_id, link, session_id) | **link→session** 出处(边从哪几轮 `indexes` 观察出来;支持多 session) | [card-link.md](card-link.md) |
| `session_marks` | (session_id, mark) | mark 元信息(last_index;撑乐观锁 + 寻址) | [session-mark.md](session-mark.md) |

索引:`idx_reviews_target`(card_id, target, created_at DESC)、`idx_reviews_card`(card_id)、`idx_card_links_target`(target_id)、`idx_card_sessions_session`(session_id)、`idx_card_sessions_mark`(session_id, mark)、`idx_position_sessions_session`(session_id)、`idx_link_sessions_session`(session_id)、`idx_session_marks_session`(session_id)。(`positions` / `card_links` 已分别按主键 `(card_id, position)` / `(card_id, link)` 聚簇,列某卡的 Position / Link 直接走 PK 前缀,无需独立索引。)

> **credence 不在任何表**:它是 `up_count`/`down_count` 的现算函数,排序 / 过滤时算,不落列 —— **Position 和 CardLink 都没有 `credence` 存储列**(见 [card.md](card.md) / [card-link.md](card-link.md))。「当下答案」(accepted)、「相不相关」(salience)、「边显不显示」同样不存 —— 召回 / read 时现算。

## vectors/(LanceDB)

`vectors/` 是 LanceDB data dir,应用层只关心 collection 的逻辑结构:

| collection | 行 | 字段 | 用途 |
|---|---|---|---|
| `cards` | 一行一卡 | `card_id` / `text`(= `issue` 分词)/ `vector` | **问题级检索**(写路径 question 撞它判 miss/hit;读路径也撞) |
| `positions` | 一行一答案 | `card_id` / `position`(p<n>) / `text`(= `claim` 分词)/ `vector` | **答案级检索**(召回撞答案文本,争议卡里贴 context 的那侧排上来) |
| `insights` | 一行一 insight | `insight_id` / `text` / `vector` | v3 `cards` collection 原样 copy 改名,insight 仍可搜(只读) |
| `rounds` | 一行一 session round | `session_id` / `idx` / `text` / `vector` | 沿用 v3 |

**embed 两处**:`cards.issue`(问题 = 答案们的适用条件)+ `positions.claim`(答案文本)。召回撞两库——问题相关 + 答案相关一起决定召回哪些 Position;**争议卡靠 claim↔context 相似度自然选边,不需要额外争议判定**。

## session mark(card_sessions 的 canonical)

v4 写路径前端 = **session mark(以写代读:逐 round 读、产 session 级感悟)**,落在 session 目录的 `marks/` —— **一条 mark 一个 `m<n>.yaml`**(`last_index` 乐观锁 + `description` + `mark` 正文 + 解析出的 `issues[]`)。mark **不是一等 id**,是 session 附属,寻址 `<session_id>#m<n>`。`issues[]` 是 card↔session 关联的 **canonical**;SQLite `card_sessions`(card→card 的出处边)+ `session_marks`(mark 元信息)都是它的派生索引。详见 [session-mark.md](session-mark.md)、[`../../works/v4/session-mark.md`](../../works/v4/session-mark.md) 与 [card-session.md](card-session.md)。

## 一张图看清「每类信息落在哪几处」

| 类别 | SQLite | 文件 | LanceDB |
|---|---|---|---|
| card 不可变核(issue) | `cards` | `card.json` | — |
| card embedding(issue) | — | — | `cards` collection |
| position embedding(claim) | — | — | `positions` collection |
| position 不可变核(claim) | `positions`(照抄 claim) | `positions/p<n>.json` | — |
| card 冗余计数(position_count/link_count) | `cards` | — | — |
| position 顶踩计数(up/down/neutral)+ review_count(冗余) | `positions` | — | — |
| position 治理(scope / `forked_from`) | `positions` | — | — |
| link 不可变核(type + target_id + claim) | `card_links`(照抄)| `links/l<n>.json` | — |
| link 顶踩计数(up/down/neutral)+ review_count(冗余) | `card_links` | — | — |
| credence / 当下答案 / 相不相关 / 边显不显示 | **不存(现算)** | — | — |
| review payload(Position 或 Link)| `reviews` | `reviews.jsonl`(卡目录下,沿用 v3) | — |
| card↔card 边(治理运行态)| `card_links` | `links/l<n>.json`(边核 canonical) | — |
| **card→session 出处**(经 mark) | `card_sessions`(派生) | `marks/m<n>.yaml` 的 `issues[]`(canonical) | — |
| **position→session 出处**(经 indexes;mark 可选) | `position_sessions`(派生) | (随 Position 的 `--source`) | — |
| **link→session 出处**(经 indexes) | `link_sessions`(派生) | (随 CardLink 的 `--source`) | — |
| mark 元信息(last_index) | `session_marks`(派生) | `marks/m<n>.yaml` | — |
| 卡 / position 事件 | — | `events.jsonl`(卡目录下) | — |
| insight(v3 遗产) | `insights` 系列表 | `insights/<bucket>/...` | `insights` collection |

## 跟 v3 filesystem 的差异

| | v3 | v4 |
|---|---|---|
| 卡目录 | `cards/<bucket>/<card_id>/card.json`(整卡一个 payload) | 同前缀,但 `card.json`(问题)+ `positions/p<n>.json`(每答案一份)+ `links/l<n>.json`(每条边一份) |
| 卡子系统 SQLite 表 | `cards` / `card_stats` / `card_source_cards` / `reviews` | `cards` / `positions` / `reviews` / `card_links` / `card_sessions` / `position_sessions` / `link_sessions` / `session_marks` |
| engagement 计数 | `card_stats.read_count` / `recall_count` 落库 | 不存(召回时现算) |
| 质量分 | 沉浮公式吃多列 | credence 现算 = f(up, down),不落列 |
| 出处 | `rounds[].session_id` 内联 | card→session `card_sessions`(mark)+ position→session `position_sessions`(indexes) |
| LanceDB | `cards`(embed insight)+ `rounds` | `cards`(embed issue)+ `positions`(embed claim)+ `insights`(v3 遗产)+ `rounds` |
| FOREIGN KEY | `card_stats` 有 FK | **全无 FK**(贯彻派生索引立场) |

## 沿用层(session / sync / logs / settings)

卡子系统以外的磁盘布局 v4 一字不改地沿用 v3,这里完整列出以便本页自洽。

### Data root

固定在 `~/.memory.talk/`,**不开 `--data-root` 参数**(详见 [`../../cli/v4/setup.md`](../../cli/v4/setup.md))。`MEMORY_TALK_DATA_ROOT` 环境变量存在,但**仅作测试 hook**(允许 tmpdir 隔离多实例),不在用户文档中暴露。

### 顶层文件

| 文件 | 内容 | 写入方 | 删除时机 |
|---|---|---|---|
| `settings.json` | 全局配置(server / embedding / search / sync / explore 等) | `setup` wizard(原子写)或手工编辑 | 用户手动 |
| `memory.db` | SQLite — 业务数据(sessions / rounds 元数据 / 卡子系统表 / 日志) | server lifespan 启动时 `init_schema` 幂等建表;各 service 写入 | 用户手动(重建走 `setup`) |
| `sync.db` | SQLite — sync 连接器自己的游标库(`sync_session_checkpoint` 表) | `SyncCheckpointStore` 在 lifespan 启动时建表;sync watcher 写入 | 删掉 = 触发下一次 server start 时全量冷扫(数据安全,因为 ingest 是 append-only + UNIQUE 兜底) |
| `server.pid` | daemon 进程 pid 文本(单行整数) | `cli server start` | `cli server stop`,或 start 探测到 pid 失活时清理 |
| `server.port` | daemon 实际监听端口(单行整数) | `cli server start` | 同 `server.pid` |

### sessions 镜像(每 session 一目录)

布局:`sessions/<source>/<id[0:2]>/<session_id>/`

- `<source>` 来自请求,如 `claude-code` / `codex`
- `<id[0:2]>` 是 `session_id` 去掉 `sess_` 前缀后的前 2 字符(bucket 散列,避免单目录过大)

| 文件 | 内容 | 写入时机 |
|---|---|---|
| `meta.json` | `session_id` / `source` / `created_at` / `metadata` / `round_count` / `synced_at` | ingest 首次创建;`round_count` / `synced_at` 变化时刷新 |
| `rounds.jsonl` | 一行一 Round JSON,**append-only** | 每次 ingest 把新增 round 追加进去。strictly append-only:同 `round_id` 的内容变更不会传到这里,sync 的 `read_after` 只产出 strictly-new round |
| `events.jsonl` | session 生命周期事件(`imported` / `rounds_appended` / `vector_index_failed` 等) | 各路径触发时追加 |
| `marks/` | **v4 新增**:逐 round 注解(见 [session-mark.md](session-mark.md)) | session mark 写入时 |

完整 session 结构(`sessions` 表列、Round / ContentBlock、cursor 三元组)见 [session.md](session.md)。

### sync.db(SQLite)

sync watcher 自己的状态库,跟 memory.db 分文件存。

| 表 | 粒度 | 用途 |
|---|---|---|
| `sync_session_checkpoint` | `(source, location, session_id)` | 每个上游 session 的 `sha256` + `last_round_id` + `line_offset` + `updated_at`。**source 是 adapter 名(`claude-code` / ...),`session_id` 是平台原始 id 不含 `sess_` 前缀** |

这里只回答一个问题:"我上次同步这个上游 session 到什么位置了"。删除 sync.db 不影响 memory.db,只会触发下一次启动重新冷扫所有上游 session。

### logs/

| 路径 | 内容 |
|---|---|
| `logs/search/<YYYY-MM-DD>.jsonl` | search 审计,**UTC 日切分**,每行一条完整 search 响应快照。老化按 `settings.search.search_log_retention_days`(默认 `0` = 永不老化) |
| `logs/sync/watch.log` | sync watcher 细粒度日志(每个文件事件 / append 结果 / 冲突 / backfill milestones) |
| `logs/server.log`(`server.log`) | uvicorn + memorytalk app 主日志 |

### 启动时确保的目录

server 启动 / `setup` 完成时,`Config.ensure_dirs` 会 `mkdir -p`:`~/.memory.talk/`、`vectors/`、`sessions/`、`cards/`、`logs/`、`logs/search/`、`logs/sync/`。`memory.db` 和 `sync.db` 由各自的 store 在首次连接时自动创建;`{source}` / `{bucket}` / `{card_id}` 等子目录在第一次写入时按需建。

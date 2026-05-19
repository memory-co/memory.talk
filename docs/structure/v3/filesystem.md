# Filesystem

v3 在 data root(**固定** `~/.memory-talk/`)下产生的所有文件 / 目录清单 —— 这一页只回答"v3 到底在磁盘上放了什么"。每类内容的字段语义和不变性见对应的对象 md。

## Data root

固定在 `~/.memory-talk/`,**不开 `--data-root` 参数**(详见 [`../../cli/v3/setup.md`](../../cli/v3/setup.md))。`MEMORY_TALK_DATA_ROOT` 环境变量存在,但**仅作测试 hook**(允许 tmpdir 隔离多实例),不在用户文档中暴露。

## 全景

```
~/.memory-talk/
├── settings.json                         # 用户配置(见 settings.md)
├── memory.db                             # SQLite 主库 —— 查询主路径
├── server.pid                            # daemon 进程 pid
├── server.port                           # daemon 实际监听端口
├── sessions/<source>/<id[0:2]>/<sid>/
│   ├── meta.json                         # session 元数据
│   ├── rounds.jsonl                      # 一行一 Round,append-only
│   └── events.jsonl                      # session 生命周期事件
├── cards/<id[0:2]>/<card_id>/            # id[0:2] = ULID 部分前 2 字符(跳过 card_ 前缀)
│   ├── card.json                         # immutable payload,写一次
│   ├── events.jsonl                      # card 生命周期事件
│   └── reviews.jsonl                     # 本 card 上的 review 镜像
├── vectors/                              # LanceDB 数据目录
│   ├── cards.lance/                      # 表:cards(insight + vector)
│   └── rounds.lance/                     # 表:rounds(session round 行)
└── logs/
    └── search/
        └── <YYYY-MM-DD>.jsonl            # search 审计,UTC 日切分
```

设计原则:**SQLite 是查询主路径**(stats / 沉浮排序 / DSL / ingest 去重 / 审计);**文件层是 audit + portability**(server 死 / db 丢,文件层能重放出大部分状态);**LanceDB 是搜索召回的唯一来源**(SQLite / jsonl 不参与 FTS 或向量检索)。

## 顶层文件

| 文件 | 内容 | 写入方 | 删除时机 |
|---|---|---|---|
| `settings.json` | 全局配置(server / embedding / search / sync / explore 等) | `setup` wizard(原子写)或手工编辑 | 用户手动 |
| `memory.db` | SQLite 单文件库 | server lifespan 启动时 `init_schema` 幂等建表;各 service 写入 | 用户手动(重建走 `setup`) |
| `server.pid` | daemon 进程 pid 文本(单行整数) | `cli server start` | `cli server stop`,或 start 探测到 pid 失活时清理 |
| `server.port` | daemon 实际监听端口(单行整数) | `cli server start` | 同 `server.pid` —— 与 pid 同步写,让 `server status` 不依赖 settings.json 渲染是否成功(`${VAR}` 解析失败也能拿到活着的端口) |

### 历史遗留

| 文件 | 说明 |
|---|---|
| `sync_state.json` | v0.5 之前用来持久化 sync 的 on/off。**已迁入 `settings.sync.enabled`**。Config 加载 settings.json 时若发现这文件,会一次性 fold 进 settings 并删除原文件,后续新装不再产生(见 `config.py:_migrate_legacy_sync_state`) |

## memory.db(SQLite)

DDL 单点:[`repository/schema.py`](../../../memorytalk/repository/schema.py)。每张表的字段语义在对应对象 md 的"存储"小节。

| 表 | 粒度 | 用途 | 详见 |
|---|---|---|---|
| `sessions` | 一行一 session | 元数据 + `cwd`(explore namespace 判断字段) | [session.md](session.md) |
| `rounds_index` | (session_id, round_id) | round 的 `content_hash` + `idx` 续号 —— **不含 round 文本** | [session.md](session.md) |
| `ingest_log` | 一行一 session | `sha256` + `last_ingest`,sync 增量去重 | [session.md](session.md) |
| `cards` | 一行一 card | `insight` + `rounds` JSON + `created_at` | [talk-card.md](talk-card.md) |
| `card_stats` | 一行一 card | 6 个计数器 + `updated_at` | [talk-card.md](talk-card.md) |
| `card_source_cards` | (card_id, seq) | `source_cards[]` 展平存 | [talk-card.md](talk-card.md) |
| `reviews` | 一行一 review | `card_id` / `session_id` / `indexes` / `score` / `comment` | [review.md](review.md) |
| `recall_log` | (session_id, card_id) | recall 同 session 内去重 | — |
| `search_log` | 一行一次 search | `response_json` blob,完整审计快照 | [search-result.md](search-result.md) |

**round 全文不在 SQLite** —— 落在 `rounds.jsonl`(完整结构) + LanceDB `rounds` 表(text + vector)。SQLite 只挂 (session_id, round_id, idx, content_hash) 做续号 / 覆写检测。

## sessions 镜像(每 session 一目录)

布局:`sessions/<source>/<id[0:2]>/<session_id>/`

- `<source>` 来自请求,如 `claude-code` / `codex`
- `<id[0:2]>` 是 `session_id` 去掉 `sess_` 前缀后的前 2 字符(bucket 散列,避免单目录过大)

| 文件 | 内容 | 写入时机 |
|---|---|---|
| `meta.json` | `session_id` / `source` / `created_at` / `metadata` / `round_count` / `synced_at` | ingest 首次创建;`round_count` / `synced_at` 变化时刷新 |
| `rounds.jsonl` | 一行一 Round JSON,**append-only** | 每次 ingest 把新增 round 追加进去;**平台覆写已存 round 的不写入**(`rounds_overwrite_skipped` 事件) |
| `events.jsonl` | session 生命周期事件 | 各路径触发时追加 |

**events.jsonl 实际写入的事件**(代码 grep):

| event | 触发点 | 关键字段 |
|---|---|---|
| `imported` | 首次 ingest 一个 session | `round_count`, `sha256` |
| `rounds_appended` | 追加 ingest,有新增 round | `added`, `overwrite_skipped` |
| `rounds_overwrite_skipped` | 平台对已存 round 做了内容覆写 | `indexes` |
| `card_extracted` | 一张 card 引用了本 session 的 round | `card_id` |
| `vector_index_failed` | LanceDB 写入失败(best-effort 不阻塞 ingest) | `error`, `affected_indexes` |

## cards 镜像(每 card 一目录)

布局:`cards/<id[0:2]>/<card_id>/`,其中 `<id[0:2]>` 是 `card_id` ULID 部分的前 2 字符(代码里写作 `card_id[5:7]` —— 跳过固定 `card_` 前缀)。

| 文件 | 内容 | 写入时机 |
|---|---|---|
| `card.json` | immutable payload + `created_at` | card 创建时,**写一次,不再改** |
| `events.jsonl` | card 生命周期事件 | 各路径触发时追加 |
| `reviews.jsonl` | 一行一 review JSON 镜像 | `POST /v3/reviews` 时与 SQLite 双写 |

**events.jsonl 实际写入的事件**:

| event | 触发点 | 关键字段 |
|---|---|---|
| `created` | card 创建 | `insight_preview`, `round_count`, `source_count` |
| `read` | `POST /v3/read` 命中本 card | `read_at` |
| `reviewed` | 本 card 收到一条 review | `review_id`, `score`, `session_id`, `indexes` |
| `card_linked` | 本 card 被另一张 card 在 `source_cards` 里引用 | `from_card`, `relation` |
| `vector_index_failed` | LanceDB 写入失败(best-effort) | `error` |

> `recall` **不写 events.jsonl**(只更新 SQLite `recall_log` + bump `card_stats.recall_count`)—— review.md / talk-card.md 列出的 `recalled` 事件是历史措辞,以本表为准。

## vectors/(LanceDB)

`vectors/` 是 LanceDB 的 data dir,内部具体文件由 LanceDB 自管(`*.lance/`、`_versions/`、manifest 等),应用层只关心两张表的逻辑结构:

| 表 | 行 | 字段 | 索引 |
|---|---|---|---|
| `cards` | 一行一 card | `card_id` / `text`(insight 经 jieba 分词)/ `vector` | FTS5 + 向量 |
| `rounds` | 一行一 session round | `session_id` / `idx` / `role` / `text`(分词)/ `vector` | FTS5 + 向量 |

Schema 定义在 [`provider/lancedb.py`](../../../memorytalk/provider/lancedb.py)。**向量维度由 `settings.embedding.dim` 决定**,改了之后 schema 不兼容,`setup` wizard 会检出并触发 embedding 全量重算(就地刷向量库)。

## logs/search/

`logs/search/<YYYY-MM-DD>.jsonl`,**UTC 日切分**,每行一条完整 `SearchLog`(包含整个 `results[]` 快照)。

每次 `POST /v3/search` 在两处双写:
1. SQLite `search_log` 表(`response_json` blob)
2. 当日 jsonl 文件

老化按 `settings.search.search_log_retention_days`(默认 `0` = 永不老化),按行 + 按天文件粒度清。详见 [search-result.md#searchlog](search-result.md#searchlog服务端审计)。

## 启动时确保的目录

server 启动 / `setup` 完成时,`Config.ensure_dirs` 会 `mkdir -p`:

- `~/.memory-talk/`
- `vectors/`
- `sessions/`
- `cards/`
- `logs/search/`

`memory.db` 由 SQLite 在首次连接时自动创建;`{source}` / `{bucket}` / `{card_id}` 等子目录在第一次写入时按需建。

## 一张图看清"每类信息落在哪几处"

| 类别 | SQLite | 文件 | LanceDB |
|---|---|---|---|
| session 元数据 | `sessions` | `meta.json` | — |
| session round 全文 | — | `rounds.jsonl` | `rounds` 表 |
| session round 索引(无文本) | `rounds_index` | — | — |
| session 事件 | — | `events.jsonl` | — |
| ingest 进度 | `ingest_log` | — | — |
| card payload(insight / rounds / source_cards / created_at) | `cards` + `card_source_cards` | `card.json` | — |
| card embedding | — | — | `cards` 表 |
| card stats(6 计数器) | `card_stats` | — | — |
| card 事件 | — | `events.jsonl` | — |
| review payload | `reviews` | `reviews.jsonl`(card 目录下) | — |
| review 落地引起的 card 事件 | — | `events.jsonl`(card 目录下,`reviewed`) | — |
| recall 去重 | `recall_log` | — | — |
| search 审计 | `search_log` | `logs/search/<date>.jsonl` | — |
| daemon 运行时坐标 | — | `server.pid` + `server.port` | — |
| 用户配置 | — | `settings.json` | — |

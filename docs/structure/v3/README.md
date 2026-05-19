# Structure (v3)

v3 的数据模型 —— 描述对象 schema、字段语义、磁盘 / 数据库布局。CLI 契约见 [`../../cli/v3/`](../../cli/v3/),HTTP 契约见 [`../../api/v3/`](../../api/v3/)。

## 对象清单

| 对象 | 形态 | 文档 |
|---|---|---|
| Talk-Card | append-only,核心记忆单元 | [talk-card.md](talk-card.md) |
| Review | append-only,对 card 的回帖(态度 + 引用 + 一句话归因) | [review.md](review.md) |
| Session | append-only(只追加 round),从平台导入的原始对话 | [session.md](session.md) |
| Search-Result | 服务端审计快照,每次 search 落一份完整响应体 | [search-result.md](search-result.md) |
| Settings | `~/.memory-talk/settings.json` 配置 | [settings.md](settings.md) |

## ID 前缀

| 对象 | 前缀 | 示例 |
|---|---|---|
| Card | `card_` | `card_01jz8k2m...` |
| Review | `review_` | `review_01jzr5kq...` |
| Session | `sess_` | `sess_187c6576-...` |
| Search 审计 | `sch_` | `sch_01K7XABC...` |

前缀 = 类型。CLI 和 API 都按前缀零成本判型分发(`read <id>` 不需要"this is a card or session?"额外参数)。

## v3 跟 v2 的对象级差异

| | v2 | v3 |
|---|---|---|
| 主对象 | card, session, link, tag | card, session, **review** |
| card↔session | 默认 link(自动生成) + 用户 link | `card.rounds[].session_id` 隐式 + `review` 显式 |
| card↔card | 用户 link(创建后可改 ttl) | `card.source_cards`(创建时确定不可改) |
| 元数据 | tag(kv 形态,session/card 共用) | 无 tag —— session/card 的语义全靠字段表达 |
| 沉浮信号 | 无 | `card.stats`(6 个计数器 + 沉浮公式) |
| TTL | card / link 各一套 | 全删,沉浮靠动力学算,不依赖 TTL 衰减 |

## 磁盘布局

```
~/.memory-talk/
├── settings.json                       # 配置(见 settings.md)
├── sync_state.json                     # sync watcher 持久化状态(enabled / 当前 totals)
├── memory.db                           # SQLite,详见各 md 的"SQLite 表"小节
├── sessions/{source}/{id[0:2]}/{sid}/
│   ├── meta.json
│   ├── rounds.jsonl
│   └── events.jsonl
├── cards/{id[0:2]}/{cid}/
│   ├── card.json                       # immutable payload
│   ├── events.jsonl                    # created / read / reviewed / recalled
│   └── reviews.jsonl                   # 本 card 上所有 review 的镜像(audit)
├── vectors/                            # 向量库目录(LanceDB)
└── logs/search/<YYYY-MM-DD>.jsonl      # 按 UTC 日期切分的 search 审计
```

**SQLite 是查询的主路径**(沉浮排序、stats 计数、DSL 过滤);**文件镜像是 audit / portability**(server 死了 / db 丢了,文件层能重放出大部分状态)。

## append-only 不变性

v3 的 card / review / session 都遵守**两条不变性**:

1. **payload 创建即冻结** —— card 的 `insight` / `rounds` / `source_cards` / review 的 `card_id` / `session_id` / `indexes` / `score` / `comment` 一旦写入不可修改。要"翻新"只能新建一张 card(在 `source_cards` 里挂 `supersedes` 关系)。
2. **stats 是 runtime 状态,不属于 payload** —— `card.stats` 是计数器集合,由 review / read / recall 落库时自动累加,后端实时维护。read 一张 card 时 stats 跟 payload 合并返回,但写入路径完全独立。

由这两条联合保证:**lineage 自然成 DAG**(card append-only + source_cards 只能引用创建时已存在的 card → 物理时序排除环)。

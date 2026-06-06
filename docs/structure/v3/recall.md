# Recall

无意识召回事件(`RecallEvent`)的对象 schema + 存储位置。

机制(file canonical / SQLite index / 派生 recall_count / 写入顺序 / dedup / SQLite 重建合约) 见 [`../../works/v3/recall-pipeline.md`](../../works/v3/recall-pipeline.md)。
`session_id` 怎么算 见 [`../../works/v3/session-namespace.md`](../../works/v3/session-namespace.md)。
跟 Review 的角色分工 见 [`../../works/v3/forum-dynamics.md`](../../works/v3/forum-dynamics.md)。

## Schema

### File 行格式(canonical · `recall.jsonl` 每行一个事件)

```json
{
  "event_id":   "01jzr5kq8h3f1d4w9m6p2x7c0a",
  "session_id": "sess-a1b2c3d4-f21fe60190b0",
  "source":     "claude-code",
  "location":   "/Users/zzz/.claude/projects",
  "ts":         "2026-05-31T06:42:01Z",
  "prompt":     "我想用 LanceDB 替换 Pinecone 怎么改",
  "top_k":      3,
  "returned": [
    {"card_id": "card_01jz8k2m", "insight": "选定 LanceDB 做向量存储"},
    {"card_id": "card_01jzp3nq", "insight": "异步数据库连接池实现"}
  ],
  "skipped": [
    {"card_id": "card_01jz9q3w", "insight": "搜索引擎核心原理"}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `event_id` | string | 是 | ULID,无前缀(只在 recall 子系统内出现) |
| `session_id` | string | 是 | canonical session_id |
| `source` | string | 是 | hook 触发时声明的 adapter 名(`claude-code` / `codex` / ...)。冗余存方便 audit 时不用反推 |
| `location` | string | 是 | hook 触发时声明的 location 路径。同上,冗余存为了 audit 自包含 |
| `ts` | string | 自动 | UTC ISO 8601,微秒精度 |
| `prompt` | string | 是 | 用户当次 hook 的输入文本,**原样保存**,不截断不归一化 |
| `top_k` | int | 是 | 本次 recall 用的 top_k 值 |
| `returned` | array of `{card_id, insight}` | 是 | 本次新返回的卡 —— **每张卡带 insight 快照**,这样事后 card 被改/删,recall.jsonl 仍能还原"当时给用户看的是什么" |
| `skipped` | array of `{card_id, insight}` | 是 | 命中但因 dedup 被跳过的卡。同样带 insight 快照 |

### SQLite `recall_event` 行格式(derived index · 为查询速度)

```sql
CREATE TABLE recall_event (
  event_id      TEXT PRIMARY KEY,
  session_id    TEXT NOT NULL,
  prompt        TEXT NOT NULL,
  ts            TEXT NOT NULL,
  returned_ids  TEXT NOT NULL,           -- JSON array of card_ids only (no insight)
  skipped_ids   TEXT NOT NULL            -- JSON array of card_ids only
);
CREATE INDEX idx_recall_event_session_ts
  ON recall_event(session_id, ts DESC);
```

SQLite 是 file 字段的子集,**少**:
- `source` / `location` —— 查询时用不上,要 audit 直接读 file
- `top_k`
- `returned[*].insight` / `skipped[*].insight` —— 现算更便宜:`recall read` 展示时 JOIN cards 表拿当前 insight

## 路径布局

```
~/.memory.talk/
└── sessions/<source>/<sid[0:2]>/<sid>/
    ├── meta.json        ← sync 写
    ├── rounds.jsonl     ← sync 写
    ├── events.jsonl     ← sync / review / card 生命周期事件
    └── recall.jsonl     ← recall hook 每次追加一行(canonical)
```

`<sid[0:2]>` 是 canonical session_id 的前 2 个字符,沿用现有 sessions 目录分片约定。

## 跟其它对象的关系

```
RecallEvent
  │
  ├── session_id ──────► Session
  │
  ├── returned_ids[] ──► Card(本次新返回的)
  │
  └── skipped_ids[]  ──► Card(命中但被去重的)
```

单向引用:RecallEvent 提到 card_id / session_id,但 card / session 本身**不存反向链** —— card 是否被 recall 过、被 recall 几次,**始终现算**。

`recall_event` 不暴露独立 REST 资源 —— 没有 `GET /v3/recall-events/{id}`。它没有"作为对象被检索"的需求,只通过 [`../api/v3/recall.md`](../../api/v3/recall.md) 的 list / read 视角访问。

# Session

从平台导入的一段原始对话。append-only,只追加 round,**不回写**已有 round 的内容。

`session_id` 算法 / sync 机制 / round 写入合约 / 向量索引补齐 见:
- [`../../works/v3/session-namespace.md`](../../works/v3/session-namespace.md)
- [`../../works/v3/sync-pipeline.md`](../../works/v3/sync-pipeline.md)
- [`../../works/v3/session-rounds-write.md`](../../works/v3/session-rounds-write.md)
- [`../../works/v3/index-backfill.md`](../../works/v3/index-backfill.md)

## Schema

```json
{
  "session_id": "sess-15f0a7fb-f21fe60190b0",
  "source": "claude-code",
  "location": "/home/user/.claude/projects",
  "location_label": "claude-code@~/.claude/projects",
  "created_at": "2026-04-10T14:30:00Z",
  "metadata": {
    "cwd": "/home/user/myapp",
    "project_id": "187c6576-...",
    "model": "claude-opus-4-7"
  },
  "tags": {
    "project": "billing",
    "status": "wip"
  },
  "rounds": [
    {
      "index": 1,
      "round_id": "da33fa35",
      "parent_id": null,
      "timestamp": "2026-04-10T14:30:05Z",
      "speaker": "user",
      "role": "human",
      "content": [{"type": "text", "text": "向量库选型,ChromaDB 和 LanceDB 哪个好?"}],
      "is_sidechain": false,
      "cwd": "/home/user/myapp"
    }
  ],
  "round_count": 20,
  "synced_at": "2026-04-16T08:00:00Z"
}
```

## 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | canonical 形式 `sess-<8-char loc8>-<last UUID segment>` |
| `source` | string | 来源平台(`claude-code` / `codex` / `openclaw` / ...) |
| `location` | string | 该 source 的端点定位符 —— 文件型 adapter 是绝对路径,HTTP 型是 base URL。**和 `source` 一起构成 endpoint 唯一键** |
| `location_label` | string\|null | 可读的端点别名,出现在 CLI 状态表 / 日志的 `<source>@<label>` 里 |
| `created_at` | string | 对话创建时间(取第一条 round 的时间戳) |
| `metadata` | object | 平台特有扩展。`metadata.cwd` 在 explore namespace 判断里有特殊作用 |
| `rounds` | Round[] | 对话轮次,通过 `parent_id` 形成链表(支持分叉) |
| `round_count` | integer | 总轮次数 |
| `synced_at` | string | 最近一次 sync 落库的时间 |
| `tags` | object | 0.8.x 新字段。string→string 字典,用户层面的标签。约束:key 匹配 `^[a-zA-Z][a-zA-Z0-9_.-]*$`,value ≤ 200 char,单 session 总 key 数 ≤ 50 |

`metadata.cwd` 跟 explore 的交互见 [`../../works/v3/explore-cwd-suppression.md`](../../works/v3/explore-cwd-suppression.md)。

## Round(Session 中)

Session 的 Round 是原始对话的忠实记录,保留完整结构。

| 字段 | 类型 | 说明 |
|---|---|---|
| `index` | integer | 会话内 1-based 自增编号(从 1 开始,gap-free)。是 `POST /v3/cards` 和 `POST /v3/reviews` 引用 round 的键 |
| `round_id` | string | 唯一标识(对应平台的 uuid) |
| `parent_id` | string\|null | 前一个 round 的 id;首条为 null。形成链表,支持分叉 |
| `timestamp` | string\|null | 时间戳 |
| `speaker` | string | 物理身份(谁在说) |
| `role` | string | 逻辑身份(`human` / `assistant` / `system` / `tool`) |
| `content` | ContentBlock[] | 内容块列表 |
| `is_sidechain` | boolean | 是否分支对话,默认 false |
| `cwd` | string\|null | 当前工作目录 |
| `usage` | object\|null | token 消耗(仅 assistant round 有),含 `input_tokens` / `output_tokens` |

### ContentBlock

| type | 字段 | 说明 |
|---|---|---|
| `text` | `text` | 文本内容 |
| `code` | `language`, `text` | 代码块 |
| `thinking` | `thinking` | AI 思考过程 |

工具调用(claude-code 的 tool_use / tool_result)按 adapter 的映射规则展开成两条独立 round,见 v2 [session.md](../v2/session.md#工具调用场景) —— v3 沿用 v2 映射约定。

## 存储

### 文件(canonical)

```
sessions/{source}/{id[0:2]}/{session_id}/
├── meta.json           # session_id / source / created_at / metadata / round_count / synced_at
├── rounds.jsonl        # 每行一个 Round JSON,append-only
└── events.jsonl        # imported / rounds_appended (v3 不再有 overwrite-skipped)
```

`{id[0:2]}` 是 session_id 的前 2 字符(canonical 形式)。

### SQLite(`memory.db`)

```sql
CREATE TABLE sessions (
  session_id              TEXT PRIMARY KEY,
  source                  TEXT NOT NULL,
  location                TEXT NOT NULL DEFAULT '',
  location_label          TEXT,
  cwd                     TEXT,                -- = metadata.cwd
  created_at              TEXT NOT NULL,
  synced_at               TEXT NOT NULL,
  metadata                TEXT NOT NULL DEFAULT '{}',
  tags                    TEXT NOT NULL DEFAULT '{}',
  round_count             INTEGER NOT NULL DEFAULT 0,
  last_round_id           TEXT,                -- ingest 的乐观锁游标
  -- 向量索引追踪(LanceDB rounds 表)
  indexed_round_count     INTEGER NOT NULL DEFAULT 0,
  last_index_error        TEXT,
  last_index_attempted_at TEXT
);

CREATE INDEX idx_sessions_cwd ON sessions(cwd);
CREATE INDEX idx_sessions_source ON sessions(source);
CREATE INDEX idx_sessions_created ON sessions(created_at);
CREATE INDEX idx_sessions_endpoint ON sessions(source, location);
```

**没有 `rounds` SQL 表**。round 数据走两条路:`rounds.jsonl` 是 source of truth(给 read 用),LanceDB rounds 表是 FTS + vector 索引(给 search / recall 用)。SQLite 这一层只关心"我有这个 session 没"和"它的游标"。

### SQLite(`sync.db`)— 跟 memory.db 分库

```sql
CREATE TABLE sync_session_checkpoint (
  source         TEXT    NOT NULL,
  location       TEXT    NOT NULL DEFAULT '',
  session_id     TEXT    NOT NULL,        -- 平台原始 id,**不含 sess- 前缀**
  sha256         TEXT    NOT NULL,
  last_round_id  TEXT,
  line_offset    INTEGER NOT NULL DEFAULT 0,
  updated_at     TEXT    NOT NULL,
  PRIMARY KEY (source, location, session_id)
);
```

`sync.db` 是 watcher 私有缓存,跟业务 `memory.db` 分库。删了不影响业务,只会触发下一次启动重新冷扫。详见 [sync-pipeline.md § sync.db checkpoint](../../works/v3/sync-pipeline.md#syncdb-checkpoint)。

## 跟其它对象的关系

```
Session
  │
  ├── rounds[].index ──► Card.rounds[].(session_id, index)  (card 引用 round)
  │                ─►   Review.indexes  (review 引用 round 范围)
  │
  └── metadata.cwd ────► explore namespace 判断
```

session **不被任何对象直接 supersede / fork** —— 它是只读的历史记录,平台覆写也只是"跳过不写"而不是回写。

# Session

从平台导入的一段原始对话。由 sync watcher 实时落库(对应 v3 `POST /v3/sessions` ingest 端点)。append-only,只追加 round,**不回写**已有 round 的内容。

## Schema

```json
{
  "session_id": "sess_187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "source": "claude-code",
  "created_at": "2026-04-10T14:30:00Z",
  "metadata": {
    "cwd": "/home/user/myapp",
    "project_id": "187c6576-...",
    "model": "claude-opus-4-7"
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
| `session_id` | string | 唯一标识,形如 `sess_<平台原始 id>`。前缀由服务端入库时加上(平台文件名不带前缀) |
| `source` | string | 来源平台(`claude-code` / `codex` / 后续扩展) |
| `created_at` | string | 对话创建时间(取第一条 round 的时间戳) |
| `metadata` | object | 平台特有扩展。**`metadata.cwd`** 字段在 explore namespace 判断里有特殊作用(见下方) |
| `rounds` | Round[] | 对话轮次,通过 `parent_id` 形成链表(支持分叉) |
| `round_count` | integer | 总轮次数 |
| `synced_at` | string | 最近一次 sync 落库的时间 |

**v3 跟 v2 的差异**:v3 session schema **没有 `tags` 字段** —— tag 整套机制在 v3 下线。其它字段保持不变。

### metadata.cwd

`metadata.cwd` 是 session 第一条 round 的 `cwd`(Claude Code 等平台在 session 元数据里自带的字段)。explore 用它做 namespace 判断:

- `metadata.cwd` startswith `settings.explore.cwd` → 这条 session 属于 explore namespace
- 反之 → 普通 work session

CLI `explore list` / `pending` / `resume` 都按这条规则筛选,不再依赖 tag(详见 [`../../cli/v3/explore.md`](../../cli/v3/explore.md))。

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

工具调用(claude-code 的 tool_use / tool_result)按 adapter 的映射规则展开成两条独立 round,详见 v2 [session.md](../v2/session.md#工具调用场景) —— 这部分 v3 沿用 v2 映射约定。

## Index 续号规则

`index` 是会话内的稳定短编号,**是 card / review 引用 round 的键**,因此写入端必须保证它的稳定性。

1. **首次 ingest**(session 不存在):按 `append_rounds` 请求里 `rounds[]` 数组顺序赋 `1, 2, 3, ...`
2. **追加 ingest**(`append_rounds(expected_prev_round_id=X)`,X 匹配 server 的 `last_round_id`):
   - 新增的 rounds **整体追加到末尾**,`index` 从 `max(existing_index) + 1` 续号
   - **不做 round_id 级别的 diff** —— sync 已经基于游标算好"哪些是新的",ingest 直接 append
3. **冲突**(`expected_prev_round_id` ≠ server 实际 `last_round_id`):返回 `status=conflict`,**不写任何 round**;sync 负责重读 + 重试
4. **sidechain round 也占号段** —— 不为 sidechain 单独编号
5. **index 一旦分配就不再变** —— card / review 引用安全性的前提

> v3 是 strictly append-only:同一个 `round_id` 内容被改了,这个事件根本不会到达 server —— sync 的 `read_after` 只产生 strictly-new round。即使到达,server 端的 UNIQUE 约束 + INSERT OR IGNORE 会把它当重复行忽略,不会覆写已有内容。

详见 [`../../api/v3/sessions.md`](../../api/v3/sessions.md)。

## 存储

### 文件(audit 镜像)

```
sessions/{source}/{id[0:2]}/{session_id}/
├── meta.json           # session_id / source / created_at / metadata / round_count / synced_at
├── rounds.jsonl        # 每行一个 Round JSON,append-only
└── events.jsonl        # imported / rounds_appended  (v3 不再有 overwrite-skipped)
```

`{id[0:2]}` 是平台 id(去掉 `sess_` 前缀后)的前 2 字符,做存储 bucket。

### SQLite(`memory.db`)

```sql
CREATE TABLE sessions (
  session_id              TEXT PRIMARY KEY,    -- 含 sess_ 前缀
  source                  TEXT NOT NULL,
  cwd                     TEXT,                -- = metadata.cwd,explore namespace 判断字段
  created_at              TEXT NOT NULL,
  synced_at               TEXT NOT NULL,
  metadata                TEXT NOT NULL DEFAULT '{}',
  round_count             INTEGER NOT NULL DEFAULT 0,
  last_round_id           TEXT,                -- ingest 的乐观锁游标
  -- 向量索引追踪(LanceDB rounds 表)。indexed_round_count < round_count
  -- 即 degraded,后台 backfill task 会拣起来重 embed。
  indexed_round_count     INTEGER NOT NULL DEFAULT 0,
  last_index_error        TEXT,                -- 最近一次 embedding 失败原因
  last_index_attempted_at TEXT
);

CREATE INDEX idx_sessions_cwd ON sessions(cwd);
CREATE INDEX idx_sessions_source ON sessions(source);
CREATE INDEX idx_sessions_created ON sessions(created_at);
```

`indexed_round_count` 是 0.6.1 加的字段,跟 `round_count` 之差就是"该 session 还有多少 round 没被向量索引"。详见 [`../api/v3/sync.md#index-health`](../../api/v3/sync.md#index-health) 和 [`docs/report/2026-05-23-search-vector-index-batch-gap.md`](../report/) 的根因分析。

> **没有 `rounds` SQL 表,也没有 `rounds_index`**。round 数据走两条路:rounds.jsonl 是 source of truth(给 read 用),LanceDB rounds 表是 FTS + vector 索引(给 search / recall 用)。SQLite 这一层只关心"我有这个 session 没"和"它的游标"。

### SQLite(`sync.db`)— 跟 memory.db 分库

```sql
CREATE TABLE sync_session_checkpoint (
  source         TEXT    NOT NULL,
  session_id     TEXT    NOT NULL,        -- 平台原始 id,**不含 sess_ 前缀**
  sha256         TEXT    NOT NULL,
  last_round_id  TEXT,
  line_offset    INTEGER NOT NULL DEFAULT 0,
  updated_at     TEXT    NOT NULL,
  PRIMARY KEY (source, session_id)
);
```

`sync.db` 是 sync watcher 自己的状态库 —— 记着"我上次看每个上游 session 的 sha256 + 最后一个 round_id + 文件 line offset",**只为 sync 增量决策服务**。删掉它不影响业务数据,只会触发下一次启动重新冷扫一遍。

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

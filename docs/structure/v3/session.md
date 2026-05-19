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

1. **首次 ingest**(`session_id` 不存在):按请求体 `rounds` 数组顺序赋 `1, 2, 3, ...`
2. **追加 ingest**(同 `session_id` 再来,且 `sha256` 变了):
   - 服务端按 `round_id` 对齐旧 / 新 rounds
   - **已存且内容未变**:保留原 `index`,**不重新编号**
   - **新增**(请求体里有、已存里没):按相对顺序从 `max(existing_index) + 1` 续号
   - **已存但内容被改**(平台覆写):**整条跳过**,原 `index` 仍指向原内容;不参与续号;产生 `rounds_overwrite_skipped` 事件
3. **sidechain round 也占号段** —— 不为 sidechain 单独编号,按数组出现顺序续号
4. **index 一旦分配就不再变** —— 这是 card / review 引用安全性的前提

详见 [`../../api/v3/sessions.md`](../../api/v3/sessions.md) 的"Index 续号规则"和 v2 [sessions.md](../../api/v2/sessions.md) 同名章节(规则一致)。

## 存储

### 文件(audit 镜像)

```
sessions/{source}/{id[0:2]}/{session_id}/
├── meta.json           # session_id / source / created_at / metadata / round_count / synced_at
├── rounds.jsonl        # 每行一个 Round JSON,append-only
└── events.jsonl        # imported / rounds_appended / rounds_overwrite_skipped
```

`{id[0:2]}` 是平台 id(去掉 `sess_` 前缀后)的前 2 字符,做存储 bucket。

### SQLite(查询主路径)

```sql
CREATE TABLE sessions (
  session_id   TEXT PRIMARY KEY,        -- 含 sess_ 前缀
  source       TEXT NOT NULL,
  cwd          TEXT,                    -- = metadata.cwd,explore namespace 判断字段
  created_at   TIMESTAMP NOT NULL,
  round_count  INTEGER NOT NULL,
  synced_at    TIMESTAMP NOT NULL,
  sha256       TEXT NOT NULL            -- 用于 sync 增量判断
);

CREATE INDEX idx_sessions_cwd ON sessions(cwd);
CREATE INDEX idx_sessions_source ON sessions(source);
CREATE INDEX idx_sessions_created_at ON sessions(created_at);

CREATE TABLE rounds (
  session_id   TEXT NOT NULL,
  index_       INTEGER NOT NULL,        -- "index" 是 SQL 保留字
  round_id     TEXT NOT NULL,
  parent_id    TEXT,
  role         TEXT NOT NULL,
  text         TEXT,                    -- 拼接后的文本(FTS 用)
  timestamp    TIMESTAMP,
  is_sidechain BOOLEAN NOT NULL DEFAULT 0,
  PRIMARY KEY (session_id, index_)
);

-- FTS 索引(SQLite FTS5)
CREATE VIRTUAL TABLE rounds_fts USING fts5(
  text,
  content='rounds',
  tokenize='unicode61'
);

-- Ingest 元数据
CREATE TABLE ingest_log (
  session_id   TEXT PRIMARY KEY,
  sha256       TEXT NOT NULL,
  last_ingest  TIMESTAMP NOT NULL
);
```

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

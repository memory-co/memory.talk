# Sync API

后端 watcher 是 settings-driven 的。**开关** = `settings.sync.enabled`(由 `memory.talk setup` 写,server 启动时 lifespan 读)。API 上只剩**一个端点**:`GET /v3/sync/status`,纯查询。

CLI 对应单命令 [`memory.talk sync`](../../cli/v3/sync.md)。

> Pre-PR-1 还有 `POST /v3/sync/start` / `POST /v3/sync/stop`,行为是同步阻塞 backfill + 写一个独立的 `sync_state.json`。现在两个端点都删了,settings.json 是 single source of truth。

## GET /v3/sync/status

### 查询参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `limit` | `5` | `recent` 列表最多保留几条 |

### 响应:`status=disabled`(`settings.sync.enabled=false`)

```json
{
  "status": "disabled",
  "index": {
    "total_sessions": 425,
    "total_rounds": 12735,
    "indexed_rounds": 12735,
    "missing_rounds": 0,
    "degraded_sessions": 0,
    "backfill_status": "idle",
    "last_index_error": null
  }
}
```

`index` 段**永远返回**(下面"index health"小节详述)—— 即便 sync 关掉,索引完整性仍然是仓库级状态。调用方应提示用户跑 `memory.talk setup` 开启 sync,或手动改 `settings.json` 后重启 server。

### 响应:`status=error`(`enabled=true` 但 watcher 没起来)

```json
{"status": "error", "error": "watcher not running", "index": {...}}
```

只在 lifespan 启动 watcher 抛异常时出现。`index` 段仍照常返回。

### 响应:`status=running`

```json
{
  "status": "running",
  "phase": "watching",
  "uptime_seconds": 7980,
  "adapters": ["claude-code", "codex"],
  "endpoints": [
    {"source": "claude-code", "location": "/home/user/.claude/projects",
     "label": "/home/user/.claude/projects", "ok": true, "reason": null},
    {"source": "codex", "location": "/home/user/.codex/sessions",
     "label": "/home/user/.codex/sessions", "ok": true, "reason": null}
  ],
  "watching": [
    {"path": "/home/user/.claude/projects", "ok": true, "reason": null},
    {"path": "/home/user/.codex/sessions",  "ok": true, "reason": null}
  ],
  "totals": {
    "discovered": 42,
    "imported": 3, "appended": 12,
    "skipped": 27, "errors": 0,
    "index_errors": 0
  },
  "totals_by_endpoint": {
    "claude-code@/home/user/.claude/projects": {
      "discovered": 30, "imported": 2, "appended": 10,
      "skipped": 18, "errors": 0, "index_errors": 0
    },
    "codex@/home/user/.codex/sessions": {
      "discovered": 12, "imported": 1, "appended": 2,
      "skipped": 9, "errors": 0, "index_errors": 0
    }
  },
  "last_event_at": "2026-05-20T14:32:18Z",
  "recent": [
    {"at": "2026-05-20T14:32:18Z", "session_id": "sess-15f0a7fb-90b0",
     "event": "rounds_appended", "endpoint": "claude-code@/home/user/.claude/projects",
     "rounds": 3}
  ],
  "index": {
    "total_sessions": 425,
    "total_rounds": 12735,
    "indexed_rounds": 12735,
    "missing_rounds": 0,
    "degraded_sessions": 0,
    "backfill_status": "idle",
    "last_index_error": null,
    "by_endpoint": [
      {"endpoint": "claude-code@/home/user/.claude/projects",
       "source": "claude-code", "location": "/home/user/.claude/projects",
       "label": "/home/user/.claude/projects",
       "sessions": 400, "rounds": 12000, "indexed": 12000,
       "missing": 0, "degraded": 0},
      {"endpoint": "codex@/home/user/.codex/sessions",
       "source": "codex", "location": "/home/user/.codex/sessions",
       "label": "/home/user/.codex/sessions",
       "sessions": 25, "rounds": 735, "indexed": 735,
       "missing": 0, "degraded": 0}
    ]
  }
}
```

| 字段 | 说明 |
|---|---|
| `phase` | `backfilling`(冷扫中)/ `watching`(冷扫完成,只走文件事件) |
| `uptime_seconds` | 距 watcher 启动的秒数 |
| `adapters[]` | 已注册 adapter 名字(legacy 字段,新代码读 `endpoints[]`) |
| `endpoints[]` | 0.7.x 新字段。每个 `(source, location)` 一行,含可达性 (`ok` / `reason`) |
| `watching[]` | 每个监听根目录的健康状态;`ok=false` 表示目录不存在但 watcher 仍在 polling |
| `totals` | 本次 lifespan 累计的跨 endpoint 总和;**server 重启会归零**(全量历史看 sessions 表 + events.jsonl)。`index_errors` 单独计数"ingest OK 但 LanceDB 索引 partial / failed",跟 `errors` 不混 |
| `totals_by_endpoint` | 0.7.x 新字段。把 `totals` 拆到每个 `<source>@<label>` 上,方便 CLI 一行一行渲染 |
| `last_event_at` | 最近一次事件时间,无事件则 null |
| `recent[]` | 最近 N 条事件(按时间倒序);**内存 ring buffer**,容量 20,server 重启清空。新增 `endpoint` 字段(0.7.x),携带 `<source>@<label>`,以及 `index_partial` / `index_failed` 事件带 `indexed` + `index_failed` 字段 |

### index health

```json
{
  "total_sessions": 425,
  "total_rounds": 12735,
  "indexed_rounds": 744,
  "missing_rounds": 11991,
  "degraded_sessions": 155,
  "backfill_status": "running",
  "last_index_error": "Client error '400 Bad Request' for url ..."
}
```

| 字段 | 来源 / 含义 |
|---|---|
| `total_sessions` | `SELECT COUNT(*) FROM sessions` |
| `total_rounds` | `SUM(round_count)`,SQLite 里的 round 总数(= jsonl 真值) |
| `indexed_rounds` | `SUM(indexed_round_count)`,真实进 LanceDB 的 round 总数 |
| `missing_rounds` | `total_rounds - indexed_rounds`,backfill 还要补的数量 |
| `degraded_sessions` | `indexed_round_count < round_count` 的 session 数 |
| `backfill_status` | `running` = 后台 task 正在补;`idle` = degraded queue 空;`disabled` = 没 embedder 或 lance(基础设施缺) |
| `last_index_error` | backfill loop 最近遇到的错误(失败 session 自己的 `last_index_error` 在 sessions 表) |
| `by_endpoint[]` | 按 `(source, location)` group 出来的 sessions/rounds/indexed/missing/degraded;CLI 拿来渲染"按 endpoint 一行"的表 |

**消费方应该如何用**:
- `degraded_sessions = 0` → 索引完整,search 看到的是全集
- `degraded_sessions > 0, backfill_status = running` → 正在补,等就行
- `degraded_sessions > 0, backfill_status = idle` → 卡住了,看 `last_index_error` 排查(常见:embedder endpoint 不可达 / API key 错 / rate limit)
- `backfill_status = disabled` → 没 embedder / 没 lance,基础设施层面的 degraded

### 副作用

只读。

### 跟 PR-1 之前 / v2 的差异

| 维度 | v2 / 旧 v3 | 现在 |
|---|---|---|
| 开关 | CLI `sync start/stop` + `sync_state.json` | `settings.sync.enabled`(setup wizard 设置) |
| 启动行为 | start 同步等 backfill 跑完才返回(可能几十秒到几分钟) | lifespan 立刻起 watcher,backfill 进**后台 task** |
| API 入口 | `POST /v3/sync/start/stop` + `GET /v3/sync/status` | **只有** `GET /v3/sync/status` |
| 内部 ingest 路径 | `POST /v3/sessions`(whole-session shim) | service 层 `ensure_session` + `append_rounds` 直接 in-process 调用,游标在 sync 自己的 sync.db |

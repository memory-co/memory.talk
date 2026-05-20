# Sync API

后端 watcher 是 settings-driven 的。**开关** = `settings.sync.enabled`(由 `memory-talk setup` 写,server 启动时 lifespan 读)。API 上只剩**一个端点**:`GET /v3/sync/status`,纯查询。

CLI 对应单命令 [`memory-talk sync`](../../cli/v3/sync.md)。

> Pre-PR-1 还有 `POST /v3/sync/start` / `POST /v3/sync/stop`,行为是同步阻塞 backfill + 写一个独立的 `sync_state.json`。现在两个端点都删了,settings.json 是 single source of truth。

## GET /v3/sync/status

### 查询参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `limit` | `5` | `recent` 列表最多保留几条 |

### 响应:`status=disabled`(`settings.sync.enabled=false`)

```json
{"status": "disabled"}
```

调用方应提示用户跑 `memory-talk setup` 开启,或手动改 `settings.json` 后重启 server。

### 响应:`status=error`(`enabled=true` 但 watcher 没起来)

```json
{"status": "error", "error": "watcher not running"}
```

只在 lifespan 启动 watcher 抛异常时出现。具体异常堆栈进 `~/.memory-talk/logs/sync/watch.log`。

### 响应:`status=running`

```json
{
  "status": "running",
  "phase": "watching",
  "uptime_seconds": 7980,
  "adapters": ["claude-code"],
  "watching": [
    {"path": "/home/user/.claude/projects", "ok": true, "reason": null}
  ],
  "totals": {
    "discovered": 42,
    "imported": 3, "appended": 12,
    "skipped": 27, "errors": 0
  },
  "last_event_at": "2026-05-20T14:32:18Z",
  "recent": [
    {"at": "2026-05-20T14:32:18Z", "session_id": "sess_187c6576-...", "event": "rounds_appended", "rounds": 3},
    {"at": "2026-05-20T14:30:02Z", "session_id": "sess_a91e2f44-...", "event": "rounds_appended", "rounds": 1},
    {"at": "2026-05-20T14:21:55Z", "session_id": "sess_5dcf9a02-...", "event": "imported", "rounds": 18}
  ]
}
```

| 字段 | 说明 |
|---|---|
| `phase` | `backfilling`(冷扫中)/ `watching`(冷扫完成,只走文件事件) |
| `uptime_seconds` | 距 watcher 启动的秒数 |
| `adapters[]` | 已注册 adapter 名字 |
| `watching[]` | 每个监听根目录的健康状态;`ok=false` 表示目录不存在但 watcher 仍在 polling |
| `totals` | 本次 lifespan 累计;**server 重启会归零**(全量历史看 sessions 表 + events.jsonl) |
| `last_event_at` | 最近一次事件时间,无事件则 null |
| `recent[]` | 最近 N 条事件(按时间倒序);**内存 ring buffer**,容量 20,server 重启清空 |

### 副作用

只读。

### 跟 PR-1 之前 / v2 的差异

| 维度 | v2 / 旧 v3 | 现在 |
|---|---|---|
| 开关 | CLI `sync start/stop` + `sync_state.json` | `settings.sync.enabled`(setup wizard 设置) |
| 启动行为 | start 同步等 backfill 跑完才返回(可能几十秒到几分钟) | lifespan 立刻起 watcher,backfill 进**后台 task** |
| API 入口 | `POST /v3/sync/start/stop` + `GET /v3/sync/status` | **只有** `GET /v3/sync/status` |
| 内部 ingest 路径 | `POST /v3/sessions`(whole-session shim) | service 层 `ensure_session` + `append_rounds` 直接 in-process 调用,游标在 sync 自己的 sync.db |

# Sync API

后端 watcher 的 control plane。三个端点:`start` / `stop` / `status`。CLI 对应 [`sync`](../../cli/v3/sync.md) 命令。

watcher 跑在 server lifespan 里,监听 adapter 配置的 session 根目录(`~/.claude/projects/...` 等),用文件系统事件 + 防抖驱动 ingest。`sync_enabled` 持久化在 `~/.memory-talk/sync_state.json`,server 重启时若为 true 自动 resume。

## POST /v3/sync/start

启动 watcher。先做一次全量 discovery 补齐(等价于历史平台文件全部过一遍 `POST /v3/sessions`),然后切到事件驱动模式。

### 请求体

无(空 body)。

### 响应:首次启动

```json
{
  "status": "started",
  "adapters": ["claude-code", "codex"],
  "backfill": {
    "discovered": 42,
    "imported": 3,
    "appended": 2,
    "skipped": 37,
    "errors": 0
  }
}
```

`backfill` 是初始全量扫描结果(细分跟 `POST /v3/sessions` 的 `action` 取值一致)。

### 响应:已在运行(no-op)

```json
{
  "status": "already_running",
  "adapters": ["claude-code", "codex"],
  "uptime_seconds": 7980
}
```

已在运行时再调 `start` 不重新扫描,直接返回当前状态。

### 副作用

- `sync_state.json` 里 `sync_enabled` 置 true(server 重启自动 resume)
- 启动 watchdog Observer,绑定到每个 adapter 暴露的根目录
- 立刻跑一次 backfill(阻塞,完成后才响应) —— 大库可能耗时几秒到几十秒

### 错误

| 情况 | 状态 |
|---|---|
| adapter 根目录全部不存在 | **不报错**,启动成功,watcher 用 polling fallback;`adapters` 里仍列,backfill discovered=0 |

## POST /v3/sync/stop

停止 watcher。已落盘数据不动;`sync_enabled` 置 false,server 重启不再 resume。

### 请求体

无。

### 响应:正在运行

```json
{
  "status": "stopped",
  "uptime_seconds": 20460,
  "totals": {
    "imported": 7,
    "appended": 12,
    "overwrite_warnings": 0,
    "errors": 0
  }
}
```

`totals` 是本次 start → stop 窗口的累计。

### 响应:未运行(no-op)

```json
{"status": "not_running"}
```

### 副作用

- `sync_state.json` 里 `sync_enabled` 置 false
- 摘掉 watchdog Observer,清空内存里的 `recent` ring buffer
- 落盘数据(sessions / cards / reviews / SQLite)**完全不动** —— stop 不擦除任何已 sync 内容

## GET /v3/sync/status

查 watcher 状态 + 累积 stats + 最近事件。

### 查询参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `limit` | `5` | `recent` 列表最多保留几条 |

### 响应:running

```json
{
  "status": "running",
  "uptime_seconds": 7980,
  "adapters": ["claude-code", "codex"],
  "watching": [
    {"path": "/home/user/.claude/projects", "ok": true},
    {"path": "/home/user/.codex/sessions", "ok": false, "reason": "missing"}
  ],
  "totals": {"imported": 7, "appended": 12, "overwrite_warnings": 0, "errors": 0},
  "last_event_at": "2026-05-18T14:32:18Z",
  "recent": [
    {"at": "2026-05-18T14:32:18Z", "session_id": "sess_187c6576-...", "event": "rounds_appended", "rounds": 3},
    {"at": "2026-05-18T14:30:02Z", "session_id": "sess_a91e2f44-...", "event": "rounds_appended", "rounds": 1},
    {"at": "2026-05-18T14:21:55Z", "session_id": "sess_5dcf9a02-...", "event": "imported", "rounds": 18},
    {"at": "2026-05-18T13:58:11Z", "session_id": "sess_187c6576-...", "event": "rounds_appended", "rounds": 2},
    {"at": "2026-05-18T13:45:33Z", "session_id": "sess_c0a4781b-...", "event": "rounds_overwrite_skipped", "rounds_skipped": 2}
  ]
}
```

| 字段 | 说明 |
|---|---|
| `status` | `running` / `stopped` |
| `uptime_seconds` | 距 watcher 启动的秒数 |
| `adapters` | 已注册 adapter 名字列表 |
| `watching[]` | 每个监听根目录的健康状态;`ok=false` + `reason=missing` 表示目录不存在,watcher 用 polling fallback |
| `totals` | 本次 start → 现在 的累计 stats |
| `last_event_at` | 最近一次事件时间;无事件则 null |
| `recent[]` | 最近 N 条事件(按时间倒序);**server 内存 ring buffer**,server 重启清空。完整历史看 SQLite `ingest_log` 表 |

### 响应:stopped

```json
{
  "status": "stopped",
  "last_run": {
    "start": "2026-05-18T09:12:00Z",
    "stop": "2026-05-18T14:48:00Z",
    "duration_seconds": 20160,
    "totals": {"imported": 7, "appended": 12, "overwrite_warnings": 0, "errors": 0}
  }
}
```

stopped 时也回显最近一次跑的统计(从 SQLite 算),如果 server 启动以来从未跑过则 `last_run` 为 null。

### 副作用

只读端点,无副作用。

### 跟 v2 的差异

v2 **完全没有 sync API** —— sync 是 CLI 胶水,读文件后直接打 `POST /v2/sessions`。v3 把整个机制内化到 server,sync API 成为这套机制的 control plane。

| 维度 | v2 | v3 |
|---|---|---|
| 触发方式 | 用户跑 `memory-talk sync` 命令 | 后端 watcher 持续监听 |
| API 入口 | `POST /v2/sessions`(直接 ingest) | `POST /v3/sync/start/stop` + `GET /v3/sync/status` + 内部调 `POST /v3/sessions` |
| 状态持久化 | 无(每次跑完就结束) | `sync_state.json`(`sync_enabled` 跨重启) |
| 事件可视 | CLI 一次性返回 stats | `GET /v3/sync/status` 任意时刻查 |

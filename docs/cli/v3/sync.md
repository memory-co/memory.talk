# sync

后端 watchdog 实时同步。**单命令 + settings-driven**:

```bash
memory-talk sync [--json] [--limit N]
```

显示当前 watcher 状态。**没有 start / stop 子命令** —— 开关在 `settings.json` 的 `sync.enabled`,通过 `memory-talk setup` 设置或直接改文件后重启 server 生效。

需要 `server` 在跑;CLI 通过 HTTP 调 `GET /v3/sync/status`,连不上就报错退出。

## 模型

```
                              ┌───── memory-talk server lifespan ──────┐
adapter session 目录            │                                       │
  (~/.claude/projects/...) ───→ watchdog Observer ── debounce ──┐       │
                              │                                 │       │
                              │  initial cold-scan (后台 task)  │       │
                              │   ↓                             ↓       │
                              │   adapter.read_after(file, last_round_id, hint_offset)
                              │   ↓                                     │
                              │   IngestService.append_rounds(expected_prev_round_id)
                              │                                         │
                              │   ─→ 写 sessions/.../rounds.jsonl      │
                              │      sessions table (last_round_id)     │
                              │      LanceDB (best-effort)              │
                              │                                         │
                              │   sync.db checkpoint(sha256+last_round_id+line_offset)
                              └─────────────────────────────────────────┘

memory-talk sync ─── HTTP ───→ GET /v3/sync/status
```

- 开启入口:`settings.sync.enabled = true`(由 setup 写)→ server lifespan 启动时 spin up watcher
- watcher 内部:**先 schedule 一次冷扫 backfill 作为后台 asyncio task**(不阻塞 lifespan),同时 observer 已经在监听
- 文件 modify / create → 200ms 防抖 → `adapter.read_after(...)` 拿增量 rounds → `ingest.append_rounds(expected_prev_round_id=...)` 乐观锁 append → 更新 sync.db 游标
- 冲突(server 实际 cursor ≠ 调用方期望)→ 自动重读 + 重试 1 次 → 仍冲突就放弃这轮,error 进 watch.log,下个事件再来
- 关掉:把 `settings.sync.enabled` 改成 `false`,重启 server

## 输出

### `status=disabled`(开关关掉)

````markdown
# sync · **disabled**

hint: enable via `memory-talk setup` or set `sync.enabled` in `settings.json` and restart the server.
````

### `status=running` · `phase=watching`

````markdown
# sync · **running** · phase `watching`

| field | value |
|---|---|
| uptime | 2h 13m |
| adapters | claude-code |
| watching | `~/.claude/projects` |
| imported | 7 |
| appended | 12 |
| overwrite_warnings | 0 |
| errors | 0 |
| last_event_at | 2026-05-20 14:32:18 |

## recent

| time | session_id | event | rounds |
|---|---|---|---|
| 14:32:18 | `sess_187c6576-…190b0` | rounds_appended | +3 |
| 14:30:02 | `sess_a91e2f44-…b81c` | rounds_appended | +1 |
| 14:21:55 | `sess_5dcf9a02-…0e7f` | imported | 18 |
````

`phase` 在冷扫期间为 `backfilling`,扫完跳 `watching`。`totals` 是本次 lifespan 的累计,server 重启清零。

### `status=error`(server lifespan auto-start 抛异常)

````markdown
# sync · **error**

watcher not running
````

具体异常 traceback 在 `~/.memory-talk/logs/sync/watch.log`。

### `--json`

```json
{
  "status": "running",
  "phase": "watching",
  "uptime_seconds": 7980,
  "adapters": ["claude-code"],
  "watching": [{"path": "/home/user/.claude/projects", "ok": true, "reason": null}],
  "totals": {"discovered": 42, "imported": 3, "appended": 12, "skipped": 27, "errors": 0},
  "last_event_at": "2026-05-20T14:32:18Z",
  "recent": [
    {"at": "2026-05-20T14:32:18Z", "session_id": "sess_187c6576-...", "event": "rounds_appended", "rounds": 3}
  ]
}
```

`recent[].event` 取值:`imported` / `rounds_appended` / `error`。`recent` 是按时间倒序的 ring buffer(容量 20),server 重启清空 —— 持久流水看 `~/.memory-talk/logs/sync/watch.log`。

## 触发一次"手动全量"

把 `~/.memory-talk/sync.db` 删掉,重启 server。下次启动的 backfill 会把所有 session 都视为新游标,重新走一遍 `ensure → read_after(None) → append_rounds`。由于 ingest 是 append-only + UNIQUE on (session_id, round_id),已经存过的 round 都不会重复写入,但游标会全部刷新一遍。

## ID 规范化

平台原始 session 文件名(例如 Claude Code 给的 UUID `187c6576-…`)在写入存储时被服务端**前缀化为 `sess_`**(即 `sess_187c6576-…`)。所有 v3 命令和 API 里出现的 `session_id` 都是带前缀的形态;sync.db 里的 checkpoint key 是 `(source, raw_session_id)`(不带前缀)—— 这是 sync 视角的"上游 id"。

## 跟其他命令的边界

- **`server start/stop`**:control plane。server 是 sync 的宿主进程;server 一停 watcher 必停;server 起来时若 `settings.sync.enabled=true` 自动拉起 watcher。
- **`setup`**:setup 的 Sync section 写 `settings.sync.enabled`。改了之后跑 `server stop && server start` 即可生效;setup 也会在结尾问要不要重启。
- **`server logs`**:只 tail `server.log`(uvicorn + memorytalk app 主日志)。sync watcher 的细粒度日志(每个文件事件 / append 结果 / 冲突 / backfill milestones)单独落 `~/.memory-talk/logs/sync/watch.log`。

## 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | `error: cannot reach server`,exit 1 |
| `settings.sync.enabled=false` | `status=disabled`,exit 0(状态查询本身成功) |
| adapter 根目录不存在 | watcher 仍起,该目录在 `watching[].ok=false`;目录出现后 polling observer 自动开始监听 |
| 单个 session 处理失败 | error 进 watch.log + recent ring buffer,watcher **不退出**,继续处理下一个事件 |
| `append_rounds` 冲突 | 自动重试 1 次;仍冲突就放弃这一轮,error 日志,下个事件再来 |

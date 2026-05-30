# sync

后端 watchdog 实时同步。**单命令 + settings-driven**:

```bash
memory.talk sync [--json] [--limit N]
```

显示当前 watcher 状态。**没有 start / stop 子命令** —— 开关在 `settings.json` 的 `sync.enabled`,通过 `memory.talk setup` 设置或直接改文件后重启 server 生效。

需要 `server` 在跑;CLI 通过 HTTP 调 `GET /v3/sync/status`,连不上就报错退出。

## 模型

```
                              ┌───── memory.talk server lifespan ──────┐
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

memory.talk sync ─── HTTP ───→ GET /v3/sync/status
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

hint: enable via `memory.talk setup` or set `sync.enabled` in `settings.json` and restart the server.
````

### `status=running` · `phase=watching`

````markdown
# sync · **running** · phase `watching`

| field | value |
|---|---|
| uptime | 2h 13m |
| endpoints | 2 |
| imported | 7 |
| appended | 12 |
| errors | 0 |
| index_errors | 0 |
| last_event_at | 2026-05-20 14:32:18 |

## endpoints

| source | location | ok | imported | appended | errors |
|---|---|---|---|---|---|
| claude-code | `/home/user/.claude/projects` | ✓ | 5 | 10 | 0 |
| codex       | `/home/user/.codex/sessions`  | ✓ | 2 | 2  | 0 |

## index health

| field | value |
|---|---|
| sessions | 425 |
| rounds | 12735 (all indexed) |
| backfill | `idle` |

### by endpoint

| endpoint | sessions | rounds | indexed | missing | degraded |
|---|---|---|---|---|---|
| `claude-code@/home/user/.claude/projects` | 400 | 12000 | 12000 | 0 | 0 |
| `codex@/home/user/.codex/sessions`        |  25 |   735 |   735 | 0 | 0 |

## recent

| time | session_id | event | rounds |
|---|---|---|---|
| 14:32:18 | `sess-15f0a7fb-…190b0` | rounds_appended | +3 |
| 14:30:02 | `sess-15f0a7fb-…b81c`  | rounds_appended | +1 |
| 14:21:55 | `sess-d68dd382-…0e7f`  | imported | 18 |
````

`endpoints` 表只在多 endpoint 时才真正有比较价值;单 endpoint 安装也会显示,只是和顶层 totals 重复。`by endpoint` 索引健康分布只在 >1 个 endpoint 时渲染。

`phase` 在冷扫期间为 `backfilling`,扫完跳 `watching`。`totals` 是本次 lifespan 的累计,server 重启清零。

### `status=error`(server lifespan auto-start 抛异常)

````markdown
# sync · **error**

watcher not running
````

具体异常 traceback 在 `~/.memory.talk/logs/sync/watch.log`。

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

`recent[].event` 取值:`imported` / `rounds_appended` / `error`。`recent` 是按时间倒序的 ring buffer(容量 20),server 重启清空 —— 持久流水看 `~/.memory.talk/logs/sync/watch.log`。

## 触发一次"手动全量"

把 `~/.memory.talk/sync.db` 删掉,重启 server。下次启动的 backfill 会把所有 session 都视为新游标,重新走一遍 `ensure → read_after(None) → append_rounds`。由于 ingest 是 append-only + UNIQUE on (session_id, round_id),已经存过的 round 都不会重复写入,但游标会全部刷新一遍。

## ID 规范化(0.7.x)

session_id 由 SyncWatcher / adapter 在 mint 阶段算好:

```
session_id = "sess-" + sha256("<source>#<location>")[:8] + "-" + last_segment(upstream_id)
```

`(source, location)` 一起进 8 字符 loc-hash,保证同源不同 endpoint 的 session **不会撞 id**;`last_segment` 是上游 id 最后一段 `-` 之后的内容(git short-sha 风格,人眼可读)。

sync.db checkpoint 的主键是 `(source, location, raw_session_id)`,跟 sessions 表的 sid 解耦 —— sync 视角看的是"上游文件 + 它在哪个 endpoint",sessions 表看的是 mint 后的全局唯一 sid。

> 0.6 → 0.7 升级路径:**不做数据迁移**。`rm -rf ~/.memory.talk && memory.talk setup` 重灌一遍即可,sync watcher 会从 0 重新 backfill 所有上游 session。

## 跟其他命令的边界

- **`server start/stop`**:control plane。server 是 sync 的宿主进程;server 一停 watcher 必停;server 起来时若 `settings.sync.enabled=true` 自动拉起 watcher。
- **`setup`**:setup 的 Sync section 写 `settings.sync.enabled`。改了之后跑 `server restart` 即可生效;setup 也会在结尾问要不要重启。
- **`server logs`**:只 tail `server.log`(uvicorn + memorytalk app 主日志)。sync watcher 的细粒度日志(每个文件事件 / append 结果 / 冲突 / backfill milestones)单独落 `~/.memory.talk/logs/sync/watch.log`。

## 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | `error: cannot reach server`,exit 1 |
| `settings.sync.enabled=false` | `status=disabled`,exit 0(状态查询本身成功) |
| adapter 根目录不存在 | watcher 仍起,该目录在 `watching[].ok=false`;目录出现后 polling observer 自动开始监听 |
| 单个 session 处理失败 | error 进 watch.log + recent ring buffer,watcher **不退出**,继续处理下一个事件 |
| `append_rounds` 冲突 | 自动重试 1 次;仍冲突就放弃这一轮,error 日志,下个事件再来 |

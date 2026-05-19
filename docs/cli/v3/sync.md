# sync

后端 watchdog 实时同步。v3 把 v2 "一次性 import 脚本" 改造成 **server 进程里长驻的 observer** —— CLI 只负责开关和状态查询,真正的发现 / 合并循环跑在 server lifespan 里。

需要 `server` 在跑;`sync start/stop/status` 都通过 HTTP 调 server,连不上就 `not_running` 退出。

## 模型

```
                                  ┌─────── server (memory-talk daemon) ──────┐
adapter session 目录 ── 文件事件 →   watchdog Observer ─→ 防抖 → adapter.convert
   (~/.claude/...,                     │  start/stop/status  │            │
    ~/.codex/...)                      └─── HTTP RPC ────────┘            ↓
                                              ↑                  append-only 合并
                                              │                          ↓
                                  memory-talk sync ...           sessions/ + ingest_log
```

- **`sync start`**:server 起一个 watchdog Observer,挂到每个已注册 adapter 暴露的根目录。**先做一次全量 discovery 补齐**(等价于 v2 跑一次 `sync`),然后切到事件驱动。
- **文件 create / modify** → 防抖 200ms 合并同一文件的连续写 → 调 adapter.convert → 走 [Append-only 策略](#append-only-策略) 落盘 → 在 `ingest_log` 写事件。
- **`sync stop`**:摘掉 Observer,已经落盘的数据不动。
- **状态持久化**:`sync_enabled` flag 持久化到 `~/.memory-talk/sync_state.json`。`server start` 时若 flag 为 true 自动 resume,直到显式 `sync stop` —— 用户只需要在首次安装后跑一次 `sync start`。

> v2 的阻塞式 `memory-talk sync`(一次扫一次导)在 v3 **下线**。需要"手动触发一次全量"时,跑 `sync stop && sync start` 即可,start 自带初始全量。

## sync start

启动后端 watcher。

```bash
memory-talk sync start [--json]
```

### Markdown(默认)

````markdown
**started** · adapters `claude-code, codex` · backfill `42 discovered, 3 imported, 39 skipped`
````

已在运行:

````markdown
**already_running** · adapters `claude-code, codex` · uptime `2h13m`
````

server 没起:

````markdown
**error:** server not_running — run `memory-talk server start` first
````

### JSON

```json
{
  "status": "started",
  "adapters": ["claude-code", "codex"],
  "backfill": {"discovered": 42, "imported": 3, "skipped": 39, "appended": 0, "errors": 0}
}
```

```json
{"status": "already_running", "adapters": ["claude-code", "codex"], "uptime_seconds": 7980}
```

```json
{"status": "error", "error": "server_not_running"}
```

backfill 那一段就是首次启动时的初始全量结果;**已在运行**时再跑 `sync start` 不重新扫描,直接 no-op 返回当前状态。

## sync stop

停止后端 watcher。已落盘的 session / card 不动。

```bash
memory-talk sync stop [--json]
```

### Markdown

````markdown
**stopped** · uptime `5h41m` · imported `7`, appended `12`, overwrite_warnings `0`
````

未运行:

````markdown
**not_running**
````

### JSON

```json
{
  "status": "stopped",
  "uptime_seconds": 20460,
  "totals": {"imported": 7, "appended": 12, "overwrite_warnings": 0, "errors": 0}
}
```

```json
{"status": "not_running"}
```

`totals` 是本次 start → stop 这一段窗口的累计;stop 后 `sync_state.json` 里 `sync_enabled` 置 false,server 重启不再自动 resume。

## sync status

看 watcher 状态 + 累计统计 + 最近事件。

```bash
memory-talk sync status [--json] [--limit N]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--limit` | `5` | `recent` 列表里最多保留多少条最近事件。 |

### Markdown(running)

````markdown
# sync · **running**

| field | value |
|---|---|
| uptime | 2h 13m |
| adapters | claude-code, codex |
| watching | `~/.claude/projects`, `~/.codex/sessions` |
| imported | 7 |
| appended | 12 |
| overwrite_warnings | 0 |
| errors | 0 |
| last_event_at | 2026-05-17 14:32:18 |

## recent

| time | session_id | event | rounds |
|---|---|---|---|
| 14:32:18 | `sess_187c6576-…190b0` | appended | +3 |
| 14:30:02 | `sess_a91e2f44-…b81c` | appended | +1 |
| 14:21:55 | `sess_5dcf9a02-…0e7f` | imported | 18 |
| 13:58:11 | `sess_187c6576-…190b0` | appended | +2 |
| 13:45:33 | `sess_c0a4781b-…f3d2` | overwrite_warning | (2 skipped) |
````

### Markdown(stopped)

````markdown
# sync · **stopped**

last run: 2026-05-17 09:12 → 14:48 (5h 36m)
totals: imported 7, appended 12, overwrite_warnings 0, errors 0
````

### JSON

```json
{
  "status": "running",
  "uptime_seconds": 7980,
  "adapters": ["claude-code", "codex"],
  "watching": ["/home/user/.claude/projects", "/home/user/.codex/sessions"],
  "totals": {"imported": 7, "appended": 12, "overwrite_warnings": 0, "errors": 0},
  "last_event_at": "2026-05-17T14:32:18Z",
  "recent": [
    {"at": "2026-05-17T14:32:18Z", "session_id": "sess_187c6576-...", "event": "appended", "rounds": 3},
    {"at": "2026-05-17T14:30:02Z", "session_id": "sess_a91e2f44-...", "event": "appended", "rounds": 1},
    {"at": "2026-05-17T14:21:55Z", "session_id": "sess_5dcf9a02-...", "event": "imported", "rounds": 18},
    {"at": "2026-05-17T13:58:11Z", "session_id": "sess_187c6576-...", "event": "appended", "rounds": 2},
    {"at": "2026-05-17T13:45:33Z", "session_id": "sess_c0a4781b-...", "event": "overwrite_warning", "rounds_skipped": 2}
  ]
}
```

`event` 取值跟 `ingest_log` 一致:`imported` / `rounds_appended`(Markdown 简写为 `appended`)/ `overwrite_warning` / `error`。`recent` 是按时间倒序的 ring buffer,由 server 内存维护,server 重启清空 —— 完整历史走 `ingest_log`。

## ID 规范化

平台原始 session 文件名(例如 Claude Code 给的 UUID `187c6576-875f-4e3e-8fd8-f21fe60190b0`)在写入存储时被服务端**前缀化为 `sess_`**,即 `sess_187c6576-875f-4e3e-8fd8-f21fe60190b0`。后续所有 v3 命令和 API 里出现的 `session_id` 都是带前缀的形态。`ingest_log` 的主键也是 `sess_*`。

## Append-only 策略

watcher 触发的合并只向前追加,不回写已有 round —— 跟 v2 完全一致:

- **新文件**:首次导入,完整写入,`ingest_log` 写一条 `imported` 事件。
- **哈希变了、且 round 数增长**:多出来的部分作为 **新 round** 追加到末尾,`index` 从已有最大 `index + 1` 续号。sidechain 情况下也只追加,写 `rounds_appended` 事件。
- **哈希变了、但某条已有 round 内容被改了**(平台覆写历史):打一条 **warning**(包含 `session_id` + 冲突的 `index`),**跳过这几条**,其它真正新增的 round 照常追加。**不回写已有 round 的存储内容** —— card 对这些 index 的引用保持原样,宁可存储和平台"对不齐"也不破坏已有 card。

新 session 落盘后立刻可被 `search` 命中;向量侧异步写入,几秒内生效。

## 跟其他命令的边界

- **`server start/stop`**:control plane。server 是 sync 的宿主进程,server 一停 watcher 必停;server 起来时若 `sync_enabled=true` 自动拉起 watcher。
- **`setup`**:sync 跟 setup 无关。setup 跑完用户决定何时第一次 `sync start`,start 一次以后就一直跑。

## 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | 所有子命令报 `error: server_not_running`,exit 1 |
| adapter 配置根目录不存在 | watcher 仍正常起,该 adapter 的 `watching` 列表里**显示但标注 missing**,目录出现后自动开始监听(watchdog 内置 polling fallback) |
| 单个文件 convert 失败 | 错误写 `ingest_log`,在 `status.recent` 里以 `event=error` 出现,watcher **不退出**,继续处理后续文件 |
| `sync_state.json` 损坏 | server 启动时 warn 一次,退回到 `sync_enabled=false`,等用户重新 `sync start` |

# Sync pipeline

后端 watchdog 怎么实时把平台 session 文件落到 backend,以及 cold-scan backfill、防抖、optimistic-concurrency 重试。

相关:
- CLI: [`../../cli/v3/sync.md`](../../cli/v3/sync.md)
- API: [`../../api/v3/sync.md`](../../api/v3/sync.md)
- Session 结构: [`../../structure/v3/session.md`](../../structure/v3/session.md)
- Round 写入细节: [session-rounds-write.md](session-rounds-write.md)

## 总体流程

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
```

- **开启入口**:`settings.sync.enabled = true`(由 setup 写)→ server lifespan 启动时 spin up watcher
- **watcher 内部**:**先 schedule 一次冷扫 backfill** 作为后台 asyncio task(不阻塞 lifespan),同时 observer 已经在监听
- **文件 modify / create** → 200ms 防抖 → `adapter.read_after(...)` 拿增量 rounds → `ingest.append_rounds(expected_prev_round_id=...)` 乐观锁 append → 更新 sync.db 游标
- **冲突**(server 实际 cursor ≠ 调用方期望)→ 自动重读 + 重试 1 次 → 仍冲突就放弃这轮,error 进 watch.log,下个事件再来
- **关掉**:把 `settings.sync.enabled` 改成 `false`,重启 server

## 防抖

200ms 防抖窗口。文件 modify 在 200ms 内多次 → 只触发一次 read_after。

为什么:平台(Claude Code / Codex)写 session 文件不是单次 write,而是 append + fsync 多次连续。每次都 read 会做无意义重复 IO。200ms 经验值是"用户感受不到延迟" + "覆盖典型 append burst"。

## 乐观锁:`expected_prev_round_id`

`ingest.append_rounds` 要求调用方传 `expected_prev_round_id` —— "我以为 server 这个 session 的最后一个 round 是 X"。

server 真实状态:从 `sessions.last_round_id` 查。

| 比较 | 行为 |
|---|---|
| `expected == actual` | append 新 rounds,更新 `last_round_id` |
| `expected != actual` | 返 `status=conflict`,**不写任何 round** |

冲突时调用方(SyncWatcher)做的事:

1. 重新 `adapter.read_after(file, last_round_id=actual)` 拿基于 actual 的增量
2. 再 `append_rounds(expected_prev_round_id=actual)`
3. 还是冲突 → 放弃这轮,error 进 watch.log,等下一个文件事件再来

这是"宁可少做不要做错"。冲突在实践中只会发生在并发写(多个 SyncWatcher 实例 / 手动 PATCH),memory.talk 自己的 watchdog 模型下基本不会触发。

## Cold-scan backfill

server lifespan 启动时,把已知的 adapter 根目录扫一遍,对每个 session 文件都 schedule `read_after(file, last_round_id=current)` —— 即使没有新事件触发,也补齐"server 关机期间漏的 round"。

这个 backfill 是**后台 asyncio task**,不阻塞 lifespan。`phase=backfilling`,跑完跳 `phase=watching`。

## sync.db checkpoint

`sync.db` 是 watcher 自己的状态库,跟 `memory.db`(业务数据)**分库**:

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

**为什么分库**:

- `sync.db` 是 sync watcher 的"私有缓存"。删掉它**不影响业务数据**,只会触发下一次启动重新冷扫一遍
- 业务 `memory.db` 不会因为 watcher 状态混乱被脏污
- 备份策略可以分:业务数据要备份,sync 状态丢了重建即可

`sha256` 是文件内容(或文件元数据,adapter 决定)的指纹,用来"我看过这个文件且它没变,跳过 read_after"。`line_offset` 是 jsonl-style 文件用的进度游标(读了到第 N 行)。

## ID 规范化(`session_id` mint)

session_id 由 SyncWatcher / adapter 在 mint 阶段算好:

```
session_id = "sess-" + sha256("<source>#<location>")[:8] + "-" + last_segment(upstream_id)
```

详细见 [session-namespace.md](session-namespace.md)。要点:

- `(source, location)` 一起进 8 字符 loc-hash,保证同源不同 endpoint 的 session **不会撞 id**
- `last_segment` 是上游 id 最后一段 `-` 之后的内容(git short-sha 风格,人眼可读)
- mint 是 deterministic 的 —— sync 进程崩了重跑,同一个上游文件还是落到同一个 sid

`sync.db` checkpoint 的主键是 `(source, location, raw_session_id)`,跟 `sessions` 表的 sid 解耦 —— sync 视角看的是"上游文件 + 它在哪个 endpoint",`sessions` 表看的是 mint 后的全局唯一 sid。

## 触发一次"手动全量"

把 `~/.memory.talk/sync.db` 删掉,重启 server。下次启动的 backfill 会把所有 session 都视为新游标,重新走一遍 `ensure → read_after(None) → append_rounds`。

由于 ingest 是 append-only + UNIQUE on `(session_id, round_id)`,已经存过的 round 都不会重复写入,但游标会全部刷新一遍。

## 错误处理

| 情况 | 行为 |
|---|---|
| adapter 根目录不存在 | watcher 仍起,该目录在 `watching[].ok=false`;目录出现后 polling observer 自动开始监听 |
| 单个 session 处理失败 | error 进 watch.log + recent ring buffer,watcher **不退出**,继续处理下一个事件 |
| `append_rounds` 冲突 | 自动重试 1 次;仍冲突就放弃这一轮,error 日志,下个事件再来 |

sync watcher 的细粒度日志(每个文件事件 / append 结果 / 冲突 / backfill milestones)单独落 `~/.memory.talk/logs/sync/watch.log`。

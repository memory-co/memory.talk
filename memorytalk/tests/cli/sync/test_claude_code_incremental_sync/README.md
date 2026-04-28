# test_claude_code_incremental_sync

增量 sync 的场景测试 —— 已有 session,平台文件新增了若干 round 后重新 sync。

## 场景

```
phase 1: platform_initial/ → 首次 ingest(2 个 round)
phase 2: platform_initial/ → 同样 bytes,sha256 命中,skipped
phase 3: platform_grown/   → 相同 session_id + 新追加 2 个 round 的 bytes,
                              round_id 对齐后检测到新增,append
phase 4: platform_grown/   → 同样 grown bytes 再来一次,skipped
```

## 输入

- `platform_initial/-home-user-mt/01K3A2BRG5N9F4YXH8MKPW6D7Q.jsonl` —
  2 行(user + assistant),session 的初始状态。
- `platform_grown/-home-user-mt/01K3A2BRG5N9F4YXH8MKPW6D7Q.jsonl` —
  4 行:前 2 行和 `platform_initial/` 逐字节一致(round_id b1 / b2),
  后 2 行是新增的 b3 / b4(一个带 `thinking` 块)。

> **关键不变式**:两份 jsonl 的前 2 行必须 byte-identical —— 否则服务端会把
> 它们当成"内容被 overwrite",触发 `rounds_overwrite_skipped` 而不是单纯的
> append。测试里最后有一条 `round_id == [b1,b2,b3,b4]` 的 assert 守护这个点。

## 覆盖的路径

在 `test_claude_code_full_sync` 之外,额外:
- **round_id-based 追加**:服务端按 `round_id` 对齐已存 round,新增的才被 append
- **index 续号**:新 round 从 `max(existing_index) + 1` 开始(这里是 3、4)
- **rounds.jsonl append-only**:已存行永不回写
- **`rounds_appended` 事件**:detail 含 `from_index` / `to_index` / `added_count`
- sha256 fast-path 在第二次和第四次命中(两个不同的 sha256,各命中自己那次)

## 关键断言(按阶段)

| 阶段 | CLI 输出关键字段 |
|---|---|
| 1 初 sync(initial) | `imported=1, appended=0` |
| 2 再 sync(initial) | `skipped=1`(sha256 fast-path) |
| 3 sync(grown) | `appended=1, added_count=2`(在端点响应里) |
| 4 再 sync(grown) | `skipped=1` |

phase-3 结束后对比 `expected/` 快照:
- `meta.json` → `round_count=4`、`last_sha256=grown 文件的 sha`
- `rounds.jsonl` → 4 行,idx `[1,2,3,4]`、round_id `[b1,b2,b3,b4]`
- `events.jsonl` → `[imported, rounds_appended]`
- `sqlite/sessions.json` → `round_count=4`
- `sqlite/rounds.json` → 4 行

## 和 full_sync 场景的数据隔离

两个场景 session_id 完全不同(`01K2F...` vs `01K3A...`)、各走自己的 pytest
`tmp_path`,filesystem + SQLite + LanceDB 三层都是独立 tmp dir。

## Regenerate fixture

```bash
REGENERATE_SYNC_FIXTURES=1 pytest memory_talk_v2/tests/cli/sync/test_claude_code_incremental_sync/
```

只录 phase-3 结束的快照。中间阶段的 CLI 输出是内联断言,不走 fixture。

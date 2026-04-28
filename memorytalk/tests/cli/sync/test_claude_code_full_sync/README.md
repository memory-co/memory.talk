# test_claude_code_full_sync

首次全量 sync 的场景测试。

## 场景

空的数据根 → `memory-talk sync --source=claude-code --platform-root=<fixture>`
→ 服务端首次 ingest 一个 claude-code session。

## 输入

- `platform/-home-user-mt/01K2FZQE4XGKV7J9MBN8PYRD3A.jsonl` —
  一段原始 claude-code jsonl(5 行:user / assistant / queue-operation / user / assistant)。
  `queue-operation` 是非对话噪音,adapter 需要跳过。

## 覆盖的路径

- Click argument parsing(`--source` / `--platform-root` / `--data-root`)
- `get_adapter("claude-code")` 适配器查找
- `ClaudeCodeAdapter.iter_sessions(root)` 扫描 jsonl
- CLI → httpx → FastAPI → `SessionService.ingest` 全链路(ASGI 路由,无子进程)
- 首次 ingest 的 index 续号(1..N)
- 文件落盘:`meta.json` / `rounds.jsonl` / `events.jsonl`
- SQLite 写入:`sessions` / `rounds`
- LanceDB FTS 写入
- event 发射:`imported`
- CLI 输出 JSON(counts 聚合、errors 收集)

## 关键断言

- 第 1 次 sync:CLI 输出 `{imported:1, appended:0, skipped:0, partial_append:0, errors:[]}`
- 第 2 次 sync 同样 bytes:`{imported:0, ..., skipped:1}`(sha256 fast-path 命中)
- 落盘 `meta.json` / `rounds.jsonl` / `events.jsonl` 和 SQLite 表内容逐字节对齐
  `expected/` 下的 fixture(忽略 synced_at / event_id / at 等非确定字段)

## 不覆盖

- 追加 / overwrite 检测 —— 属于 `test_claude_code_incremental_sync/` 场景

## Regenerate fixture

```bash
REGENERATE_SYNC_FIXTURES=1 pytest memorytalk/tests/cli/sync/test_claude_code_full_sync/
```

用在 adapter / schema 有意变更后,重录 golden file。regenerate 模式跑完会故意
raise,提示"取消环境变量再重跑一次确认 assert 通过"。

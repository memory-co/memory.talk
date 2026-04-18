# Session 目录结构改造

## 问题

sessions 的元数据（source, tags, created_at, metadata）只存在 SQLite 中，JSONL 文件只存 rounds。SQLite 删了元数据就丢了。

## 目标

文件系统是 source of truth。SQLite 是纯索引缓存，可删除后通过 rebuild 重建。

## 设计

### Session 目录结构

从文件变目录：

```
# 之前
sessions/{source}/{hash}/{session_id}.jsonl

# 之后
sessions/{source}/{hash}/{session_id}/
├── meta.json        # 元数据（source of truth）
└── rounds.jsonl     # 对话内容
```

**meta.json**：
```json
{
  "session_id": "abc123",
  "source": "claude-code",
  "created_at": "2026-04-10T10:00:00Z",
  "synced_at": "2026-04-18T08:00:00Z",
  "metadata": {"project": "/home/user/myapp"},
  "tags": ["claude-code", "project:myapp"],
  "round_count": 20
}
```

Cards 不改。

### rebuild 命令

`memory-talk rebuild` — 异步任务，不阻塞 CLI。

实现：
1. 删除 SQLite 文件（`relation.db`）
2. 删除 LanceDB 目录（`vectors/`）
3. 重新 init_db 建空表
4. 异步扫描 sessions/ 和 cards/ 目录，逐个写入 SQLite + LanceDB
5. TTL 全部用默认 initial 值重置

CLI 立即返回 `{"status": "rebuilding"}`，后台执行。

### Tags 持久化

tag 操作同步写回 meta.json，确保文件系统是 source of truth。

## 涉及文件

- `memory_talk/storage/files.py` — SessionFiles 改目录结构
- `memory_talk/service/sessions.py` — 写 meta.json，tag 同步文件
- `memory_talk/service/rebuild.py` — 新增
- `memory_talk/cli.py` — 新增 rebuild 命令
- 测试更新

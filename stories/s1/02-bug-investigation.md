# 一次 Bug 排查的记忆

```bash
memory-talk sync
```

```json
{
  "platforms": [
    {
      "name": "claude",
      "sessions_total": 25,
      "sessions_new": 1,
      "sessions_updated": 0,
      "rounds_new": 47
    }
  ],
  "total": {
    "sessions": 25,
    "new": 1,
    "updated": 0,
    "rounds_new": 47
  }
}
```

一个新 session，47 轮。不短。看看是什么。

```bash
memory-talk session read d8b2f4
```

这是一段 bug 排查。用户报告说 `cards create` 命令偶尔会卡住不返回。经过漫长的排查——查日志、加 print、尝试复现——最终发现是 LanceDB 在写入时如果表不存在会触发一个同步的 schema 创建，而在某些文件系统上这个操作会阻塞。解决方案是在首次 `sync` 时预创建表结构。

47 轮对话，但故事线很清晰：症状 → 排查过程 → 根因 → 修复。我要保留排查的关键转折点，而不只是结论——下次遇到类似问题，排查思路比答案更有价值。

```bash
memory-talk card create '{
  "summary": "cards create 偶发卡死的根因是 LanceDB 首次写入时同步创建表 schema，在某些文件系统上会阻塞，修复方案是预创建表结构",
  "rounds": [
    {"role": "human", "text": "memory-talk card create 有时候会卡住，大概 10 秒不返回，然后又正常了"},
    {"role": "assistant", "text": "加了计时日志后发现卡在 _ensure_table 方法。怀疑是表创建的开销。", "thinking": "卡住而非报错，说明不是异常而是阻塞。计时日志缩小范围"},
    {"role": "assistant", "text": "找到了。LanceDB create_table 在 NFS 上会触发 fsync，网络文件系统上很慢。本地 SSD 复现不了。", "thinking": "只在部分环境出现——文件系统差异是关键线索"},
    {"role": "human", "text": "我确实是在 NFS 上跑的，公司的开发机。"},
    {"role": "assistant", "text": "修复方案：首次 sync 时预创建 LanceDB 表和 schema，cards create 时直接 open_table 不再触发创建。"}
  ],
  "links": [
    {"id": "d8b2f4", "type": "session", "comment": "完整的 bug 排查过程，47 轮"},
    {"id": "01jz8k2m", "type": "card", "comment": "LanceDB 选型决策——这个 bug 是选型的后果之一"}
  ]
}'
```

```json
{"status": "ok", "card_id": "01jzp3nq"}
```

这张 card 里我跳过了大量中间轮次——r002 到 r011 是各种无果的尝试（查看系统资源、怀疑是死锁、加了一堆无用的日志），r013 到 r027 是缩小范围的过程。保留下来的五轮是排查的关键节拍：现象、定位到方法、找到根因、确认环境因素、修复方案。

我还把这张 card 链接到了之前那张 LanceDB 选型的 card。它们之间有一个隐含的关系：选了 LanceDB 是因为零依赖好部署，但这个 bug 揭示了一个之前没考虑到的代价——NFS 兼容性。下次讨论存储方案时，这两张 card 一起被召回，就能看到更完整的图景。

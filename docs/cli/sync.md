# sync

自动发现并同步所有平台的会话。

```bash
memory-talk sync
```

扫描所有已配置平台的默认目录，自动导入新会话和更新过的会话。

输出示例：

```json
{
  "platforms": [
    {
      "name": "claude",
      "sessions_total": 10,
      "sessions_new": 2,
      "sessions_updated": 1,
      "rounds_new": 87
    },
    {
      "name": "codex",
      "sessions_total": 6,
      "sessions_new": 1,
      "sessions_updated": 0,
      "rounds_new": 24
    }
  ],
  "total": {
    "sessions": 16,
    "new": 3,
    "updated": 1,
    "rounds_new": 111
  }
}
```

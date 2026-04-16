# explore

发现和导入平台对话。

## explore scan

列出未导入的 session（自动排除已导入的）。

```bash
memory-talk explore scan --source claude-code
```

输出示例：
```json
{
  "source": "claude-code",
  "new_sessions": [
    {"path": "/home/user/.claude/projects/myproject/abc123.jsonl", "hash": "a1b2c3d4e5f67890"}
  ],
  "total": 1
}
```

## explore ingest

导入单个 session 文件。

```bash
memory-talk explore ingest <SESSION_PATH>
```

输出示例：
```json
{
  "status": "ok",
  "session_id": "abc123",
  "source": "claude-code",
  "rounds": 15
}
```

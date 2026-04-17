# Session

Session 是从平台导入的一段原始对话，由 `sync` 命令写入。

## Schema

```json
{
  "session_id": "abc123",
  "source": "claude-code",
  "created_at": "2026-04-10T14:30:00Z",
  "metadata": {
    "project": "/home/user/myapp"
  },
  "tags": ["claude", "project:myapp"],
  "rounds": [
    {
      "round_id": "r001",
      "timestamp": "2026-04-10T14:30:05Z",
      "speaker": "user",
      "role": "human",
      "content": [
        {"type": "text", "text": "向量库选型，ChromaDB 和 LanceDB 哪个好？"}
      ]
    }
  ],
  "round_count": 20,
  "synced_at": "2026-04-16T08:00:00Z"
}
```

## 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 唯一标识（来源平台的文件名） |
| `source` | string | 来源平台（`claude-code` / `codex` / `openclaw`） |
| `created_at` | string | 对话创建时间（取第一条 round 的时间戳） |
| `metadata` | object | 平台特有的扩展信息（project 路径、model 等） |
| `tags` | string[] | 自由标签，`key:value` 格式 |
| `rounds` | Round[] | 对话轮次（完整结构见 [talk-card.md](talk-card.md) 中的 Round 定义） |
| `round_count` | integer | 总轮次数 |
| `synced_at` | string | 导入时间 |

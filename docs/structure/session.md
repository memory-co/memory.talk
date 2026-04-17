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
      "round_id": "da33fa35",
      "parent_id": null,
      "timestamp": "2026-04-10T14:30:05Z",
      "speaker": "user",
      "role": "human",
      "content": [
        {"type": "text", "text": "向量库选型，ChromaDB 和 LanceDB 哪个好？"}
      ]
    },
    {
      "round_id": "ddda3122",
      "parent_id": "da33fa35",
      "timestamp": "2026-04-10T14:30:10Z",
      "speaker": "assistant",
      "role": "assistant",
      "content": [
        {"type": "text", "text": "推荐 LanceDB，零依赖、嵌入式架构。"}
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
| `metadata` | object | 平台特有的扩展信息（project、model、title、agent_name、version 等） |
| `tags` | string[] | 自由标签，`key:value` 格式 |
| `rounds` | Round[] | 对话轮次，每条通过 `parent_id` 指向上一条形成链表（完整结构见 [talk-card.md](talk-card.md) 中的 Round 定义） |
| `round_count` | integer | 总轮次数 |
| `synced_at` | string | 导入时间 |

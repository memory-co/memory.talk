# Sessions API

## POST /sessions

导入一个 session。

请求体：
```json
{
  "session_id": "abc123",
  "source": "claude-code",
  "created_at": "2026-04-10T14:30:00Z",
  "metadata": {"project": "/home/user/myapp"},
  "rounds": [
    {
      "round_id": "r001",
      "speaker": "user",
      "role": "human",
      "content": [{"type": "text", "text": "..."}]
    }
  ]
}
```

Round 和 ContentBlock 结构见 [talk-card.md](../structure/talk-card.md)。

响应：
```json
{"status": "ok", "session_id": "abc123", "rounds": 15}
```

## GET /sessions

列出 sessions。

| 参数 | 说明 |
|------|------|
| `tag` | 按 tag 筛选，可多个（AND 关系） |

响应：Session 元数据数组。

## GET /sessions/:id

读取 session 的 rounds。

| 参数 | 说明 |
|------|------|
| `start` | 起始 round 索引（可选） |
| `end` | 结束 round 索引（可选） |

响应：Round 数组。

## POST /sessions/:id/tags

添加 tags。

请求体：
```json
{"tags": ["claude", "project:myapp"]}
```

## DELETE /sessions/:id/tags

移除 tags。

请求体：
```json
{"tags": ["important"]}
```

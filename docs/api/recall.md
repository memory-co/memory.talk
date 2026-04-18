# Recall API

## POST /recall

向量检索，返回语义最相关的 Talk-Card。

请求体：
```json
{
  "query": "数据库选型",
  "top_k": 5
}
```

| 字段 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | 是 | | 检索文本 |
| `top_k` | 否 | 5 | 返回结果数 |

响应：
```json
{
  "query": "数据库选型",
  "results": [
    {
      "card_id": "01jz8k2m",
      "summary": "决定用 LanceDB...",
      "session_id": "abc123",
      "ttl": 2592000,
      "distance": 0.18,
      "links": [
        {"link_id": "01jzq7rm", "id": "abc123", "type": "session", "comment": "从这段讨论中提取", "ttl": 100},
        {"link_id": "01jzq8sn", "id": "01jzp3nq", "type": "card", "comment": "后续踩了 NFS 的坑", "ttl": 85}
      ]
    }
  ],
  "count": 1
}
```

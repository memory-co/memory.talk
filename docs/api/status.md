# Status API

## GET /status

返回存储统计信息。

响应：
```json
{
  "sessions_total": 12,
  "cards_total": 47,
  "vector_provider": "lancedb",
  "relation_provider": "sqlite",
  "embedding_provider": "local"
}
```

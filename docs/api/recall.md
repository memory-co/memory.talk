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
      "distance": 0.18
    }
  ],
  "count": 1
}
```

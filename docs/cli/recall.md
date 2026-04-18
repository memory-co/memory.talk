# recall

向量检索，返回语义最相关的 Talk-Card。

```bash
memory-talk recall "<QUERY>" [--top-k N]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--top-k` | 5 | 返回结果数 |

输出示例：
```json
{
  "query": "数据库选型",
  "results": [
    {
      "card_id": "01jz...",
      "summary": "决定用 LanceDB...",
      "session_id": "abc123",
      "ttl": 2592000,
      "distance": 0.23,
      "links": [
        {"link_id": "01jzq7rm", "id": "abc123", "type": "session", "comment": "从这段讨论中提取", "ttl": 100},
        {"link_id": "01jzq8sn", "id": "01jzp3nq", "type": "card", "comment": "后续踩了 NFS 的坑", "ttl": 85}
      ]
    }
  ],
  "count": 1
}
```

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
      "distance": 0.23
    }
  ],
  "count": 1
}
```

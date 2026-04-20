# Cards API

## POST /v1/cards

创建一张 Talk-Card。自动计算 embedding 写入向量库。

请求体：
```json
{
  "summary": "决定用 LanceDB 做向量存储",
  "session_id": "abc123",
  "rounds": [
    {"role": "human", "text": "向量库选型，ChromaDB 和 LanceDB 哪个好？"},
    {"role": "assistant", "text": "推荐 LanceDB：零依赖、适合嵌入式部署。"}
  ],
  "links": [
    {"id": "abc123", "type": "session", "comment": "从这段讨论中提取"}
  ]
}
```

`card_id` 可选，不提供则自动生成 ULID。

`session_id` 可选，冗余字段方便按 session 查找。可为空——基于多个 card 合成的新 card 没有单一来源 session。

完整结构见 [talk-card.md](../../structure/v1/talk-card.md)。

响应：
```json
{"status": "ok", "card_id": "01jz8k2m"}
```

## GET /v1/cards

列出 cards。

| 参数 | 说明 |
|------|------|
| `session_id` | 按 session 筛选（可选） |

响应：Card 元数据数组。

## GET /v1/cards/:id

读取一张 card 的完整内容。

| 参数 | 说明 |
|------|------|
| `link_id` | 通过哪条 link 访问到的（可选）。传入时自动刷新该 link 的 TTL |

响应：完整 Talk-Card JSON。

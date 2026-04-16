# cards

管理 Talk-Card。

## cards create

创建一张 Talk-Card。自动计算 embedding 写入向量库。

```bash
memory-talk cards create '<JSON>'
```

JSON 字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `cognition_summary` | 是 | 一句话认知总结（embedding 锚点） |
| `compressed_rounds` | 是 | 压缩后的对话内容（≤1024 token） |
| `session_id` | 是 | 来源 session ID |
| `round_start` | 是 | 起始 round 索引 |
| `round_end` | 是 | 结束 round 索引 |
| `card_id` | 否 | 不提供则自动生成 ULID |
| `links` | 否 | CardLink 数组，创建时一并写入 |

示例：
```bash
memory-talk cards create '{
  "cognition_summary": "决定用 LanceDB 做向量存储，因为零依赖、本地文件、适合嵌入式部署",
  "compressed_rounds": "用户问向量库选型。讨论了 ChromaDB vs LanceDB...",
  "session_id": "abc123",
  "round_start": 0,
  "round_end": 5,
  "links": [
    {"target_card_id": "prev-card-id", "link_type": "temporal"}
  ]
}'
```

输出：
```json
{"status": "ok", "card_id": "01jz..."}
```

## cards get

读取一张 card 的完整内容。

```bash
memory-talk cards get <CARD_ID>
```

## cards list

列出所有 card，可按 session 筛选。

```bash
memory-talk cards list [--session-id <ID>]
```

## cards links

获取与指定 card 关联的所有 card。

```bash
memory-talk cards links <CARD_ID>
```

输出包含 `links`（关联关系列表）和 `linked_cards`（关联 card 的完整内容）。

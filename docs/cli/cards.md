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
| `summary` | 是 | 一句话认知总结（embedding 锚点） |
| `rounds` | 是 | 精简的 Round 数组，每条只有 `role` 和 `text` |
| `links` | 是 | Link 数组，所有关联（包括与 session 的关联）都在这里 |
| `card_id` | 否 | 不提供则自动生成 ULID |

`rounds` 是极度精简的对话记录，只保留谁说了什么。冗余 round 跳过，保留的文本压缩到最精炼。

`links` 统一表达所有关联。时间先后由系统根据创建时间自动计算，无需传入。

| 字段 | 说明 |
|------|------|
| `id` | 关联对象的 ID |
| `type` | `session` 或 `card` |
| `comment` | 可选，说明为什么关联 |

示例：
```bash
memory-talk cards create '{
  "summary": "决定用 LanceDB 做向量存储，因为零依赖、本地文件、适合嵌入式部署",
  "rounds": [
    {"role": "human", "text": "向量库选型，ChromaDB 和 LanceDB 哪个好？"},
    {"role": "assistant", "text": "推荐 LanceDB：零依赖、本地文件存储、适合嵌入式部署。ChromaDB 需要服务进程。"},
    {"role": "human", "text": "就用 LanceDB。"}
  ],
  "links": [
    {"id": "abc123", "type": "session", "comment": "从这个会话中提取"},
    {"id": "prev-card-id", "type": "card", "comment": "该 card 讨论了备选方案 ChromaDB"}
  ]
}'
```

中间的确认和重复轮次被跳过，保留的文本压缩到最精炼。这是记忆，不是录像。

输出：
```json
{"status": "ok", "card_id": "01jz..."}
```

## cards get

读取一张 card 的完整内容。

```bash
memory-talk cards get <CARD_ID> [--link-id <LINK_ID>]
```

`--link-id` 声明通过哪条 link 访问到的，传入时自动刷新该 link 的 TTL。

## cards list

列出所有 card，可按 session 筛选。

```bash
memory-talk cards list [--session-id <ID>]
```


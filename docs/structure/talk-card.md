# Talk-Card

Talk-Card 是 memory.talk 的核心数据结构——从对话中提炼出的记忆单元。

## Schema

```json
{
  "card_id": "01jz8k2m",
  "summary": "项目选定 LanceDB 作为向量存储方案，主要原因是零依赖、嵌入式架构",
  "rounds": [
    {"role": "human", "text": "向量库选型，ChromaDB 和 LanceDB 哪个好？"},
    {"role": "assistant", "text": "推荐 LanceDB：零依赖、本地文件存储、适合嵌入式部署。ChromaDB 需要服务进程。", "thinking": "关键考量是部署形态——Skill 嵌入式场景不能要求用户启动额外服务"},
    {"role": "human", "text": "就用 LanceDB。"}
  ],
  "links": [
    {"link_id": "01jzq7rm", "id": "f7a3e1", "type": "session", "comment": "从这段讨论中提取", "ttl": 100},
    {"link_id": "01jzq8sn", "id": "01jzp3nq", "type": "card", "comment": "后续踩了 NFS 的坑", "ttl": 85}
  ],
  "ttl": 95,
  "created_at": "2026-04-16T10:30:00Z"
}
```

## 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `card_id` | string | 自动生成 | ULID，不提供则自动生成 |
| `summary` | string | 是 | 一句话认知总结，同时作为 embedding 锚点 |
| `session_id` | string | 否 | 冗余字段，方便按 session 查找。可为空（基于多个 card 合成的新 card） |
| `rounds` | Round[] | 是 | 精简后的对话轮次（见下方 Round 结构） |
| `links` | Link[] | 是 | 与 session 和其他 card 的关联（见下方 Link 结构） |
| `ttl` | integer | 自动 | 剩余生命值，创建时设为初始值（默认 100），被 recall 命中时刷新 |
| `created_at` | string | 自动生成 | 创建时间，系统自动填充 |

## Round（Talk-Card 中）

Talk-Card 中的 round 是极度精简的——只保留谁说了什么。关键 round 保留，冗余 round 跳过，保留的文本压缩到最精炼。

| 字段 | 类型 | 说明 |
|------|------|------|
| `role` | string | `human` / `assistant` |
| `text` | string | 精简后的文本 |
| `thinking` | string\|null | 可选，关键的思考思路（精简后保留） |

与 Session 中的 Round 不同：没有 round_id、parent_id、timestamp、content block 等原始结构。这是记忆，不是录像。

Session 中完整的 Round 结构见 [session.md](session.md)。

## Link

完整结构见 [link.md](link.md)。

`cards create` 时简写为 `{id, type, comment}`，source 隐含为当前 card。读取时返回完整字段包括 `link_id` 和 `ttl`。

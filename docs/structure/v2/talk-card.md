# Talk-Card

Talk-Card 是 memory.talk 的核心数据结构——从对话中提炼出的记忆单元。

## Schema

```json
{
  "card_id": "01jz8k2m",
  "summary": "项目选定 LanceDB 作为向量存储方案，主要原因是零依赖、嵌入式架构",
  "rounds": [
    {"role": "human", "text": "向量库选型，ChromaDB 和 LanceDB 哪个好？", "session_id": "f7a3e1", "index": 11},
    {"role": "assistant", "text": "推荐 LanceDB：零依赖、本地文件存储、适合嵌入式部署。", "thinking": "关键考量是部署形态——Skill 嵌入式场景不能要求用户启动额外服务", "session_id": "f7a3e1", "index": 12},
    {"role": "human", "text": "就用 LanceDB。", "session_id": "f7a3e1", "index": 13}
  ],
  "links": [
    {"link_id": "01jzq7rm", "id": "f7a3e1", "type": "session", "comment": null, "ttl": 0},
    {"link_id": "01jzq8sn", "id": "01jzp3nq", "type": "card", "comment": "后续踩了 NFS 的坑", "ttl": 1814400}
  ],
  "ttl": 2419200,
  "created_at": "2026-04-16T10:30:00Z"
}
```

## 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `card_id` | string | 自动生成 | ULID，不提供则自动生成 |
| `summary` | string | 是 | 一句话认知总结，同时作为 embedding 锚点 |
| `rounds` | Round[] | 是 | 展开后的对话轮次（见下方 Round 结构），每条自带 `session_id` + `index` 指回源 session。可为空数组（合成 card） |
| `links` | Link[] | 是 | 与 session 和其他 card 的关联（见下方 Link 结构）。card → session 部分由服务端基于 `rounds` 里出现过的 `session_id` 自动生成 |
| `ttl` | integer | 自动 | 剩余生命值（秒）。创建时设为 `settings.ttl.card.initial`（默认 2592000 = 30 天），被 view 命中时按 `factor` 续命。`expires_at - now` 计算，可以为负（已过期） |
| `created_at` | string | 自动生成 | 创建时间，系统自动填充 |

对比 v1：删除了 `session_id` 冗余字段，改成每条 round 里自带 `session_id` + `index` 溯源——表达力更强，可引用多个 session、可跳过中间段。

## Round（Talk-Card 中）

由写入时 [`card`](../../cli/v2/card.md) 命令里 `rounds` 字段指定的 `{session_id, indexes}` 展开而来，对齐 `session.rounds[].index`。

| 字段 | 类型 | 说明 |
|------|------|------|
| `role` | string | `human` / `assistant` |
| `text` | string | 从 session 对应 round 摘出来的文本 |
| `thinking` | string\|null | 可选，关键的思考思路 |
| `session_id` | string | 该 round 来自哪个 session |
| `index` | integer | 该 round 在源 session 里的 `index` |

和 Session 中的 Round 不同：没有 round_id、parent_id、timestamp、content block 等原始结构。要追溯到原始 round，用本行的 `session_id` + `index` 直接定位源 session 的 `rounds[index]`。这是记忆，不是录像。

`session_id` 与 `index` 只是元数据，**不进入向量检索**——向量侧只 embed `summary`（以及必要时的 `text`），数字 ID 在语义检索里没意义。

Session 中完整的 Round 结构见 [session.md](session.md)。

## Link

完整结构见 [link.md](link.md)。

v2 `card` 写入时**不再接受 `links` 入参**：

- **默认 link**（`ttl = 0`）：服务端扫描 `rounds` 里出现过的 `session_id`，为每个不同的 session_id 生成一条 card → session 关联，`comment` 为 null。生死跟随 card，不独立计时，不能被 view 续命。
- **用户 link**（`ttl > 0`）：用独立的 [`link create`](../../cli/v2/link.md) 命令追加，支持 card↔card / card↔session / session↔session 任意组合，有独立 TTL，可被 view 续命。

view 返回 card 时两类 link 都在 `links` 字段里，靠 `ttl` 值区分：
- `ttl = 0`：**默认 link 的 sentinel**——不是"0 秒后过期"，而是"不参与秒级计时，跟 card 同活"。
- `ttl > 0`：活跃用户 link，单位秒。
- `ttl < 0`：已过期用户 link（view 仍返回，search 过滤掉）。

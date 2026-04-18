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

所有关联统一用 Link 表达。时间先后由系统根据 `created_at` 自动计算。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `link_id` | string | 自动生成 | Link 自身的唯一标识（ULID） |
| `id` | string | 是 | 关联对象的 ID |
| `type` | string | 是 | `session` 或 `card` |
| `comment` | string | 否 | 说明为什么关联 |
| `ttl` | integer | 否 | 剩余生命值，每次被 recall 命中时刷新，降为 0 时遗忘 |

`link_id` 是 link 自身的唯一标识。读取 card 时返回 `link_id`，后续可通过它刷新 TTL。

`cards create` 时，方向隐含为当前 card → id。读取 card 时，link 列表包含两个方向（当前 card 作为 source 和 target 的都会出现）。

### TTL 遗忘机制

Link 通过 TTL（Time To Live）实现自然遗忘：

- **创建时**：TTL 设为初始值（默认 100）
- **被访问时**：通过 `cards get --link-id <LINK_ID>` 刷新，TTL 重置为初始值
- **衰减**：每次全局衰减周期（由系统定期执行），所有 link 的 TTL 减 1
- **遗忘**：TTL 降为 0 时，link 不再出现在查询结果中（数据保留，标记为遗忘）

常用的关联会被反复 recall 命中而续命，冷门的关联自然淡忘。这模拟了人类记忆的遗忘曲线——不是删除，是逐渐想不起来。

---
name: build
description: Use when organizing imported sessions into Talk-Cards — this is the core memory-building workflow
---

# Build

把原始 session 精炼成 Talk-Card。认知工作由你（Agent）完成，CLI 只管存。**Session 是录像，Card 是记忆。**

## Steps

### 1. 找未整理的 session

```
memory-talk session list --tag unbuilt
```

### 2. 读 session 的 rounds

```
memory-talk session read <session_id>
```

也支持范围：`--start N --end M`。返回完整的 Round 数组（`round_id / parent_id / speaker / role / content[] / timestamp / cwd` 等）。

### 3. 识别话题边界

一个 session 常常跨多个话题（数据库选型 → 部署 → code review）。通读 rounds，找话题切换点，每个连贯话题段落变一张 Talk-Card。

### 4. 为每段话题创建一张 card

对每个段落：

- **压缩 rounds**：只保留关键的"谁说了什么"。寒暄、重复、确认 round 全部跳过；保留的文本压缩到最精炼。Talk-Card 中的 round 只有 `{role, text, thinking?}`，没有 `round_id / parent_id / content block` 这些 session 的原始结构。
- **写 summary**：一句话捕捉核心结论或决策。这是 embedding 锚点，也是未来 recall 的关键。**"决定 X 因为 Y"** 比 **"讨论了数据库选项"** 好。
- **识别 links**：
  - 至少一条到 **source session** 的 link（`type: "session"`）表明这张 card 的来源。
  - 有相关 card 时加到 **其他 card** 的 link（`type: "card"`）—— 比如同一话题在别的 session 讨论过、这张 card 的结论是另一张的前提，等等。关联的语义写在 `comment` 里，自由文本。

**创建 card：**

```
memory-talk card create '{
  "summary": "决定用 LanceDB 做向量存储，因为零依赖、本地文件、适合嵌入式部署",
  "rounds": [
    {"role": "human", "text": "向量库选型，ChromaDB 和 LanceDB 哪个好？"},
    {"role": "assistant", "text": "推荐 LanceDB：零依赖、本地文件存储。ChromaDB 需要服务进程。", "thinking": "关键是部署形态——Skill 场景不能要求用户起额外服务"},
    {"role": "human", "text": "就用 LanceDB。"}
  ],
  "links": [
    {"id": "abc123", "type": "session", "comment": "从这段讨论中提取"},
    {"id": "01jzp3nq", "type": "card", "comment": "后续踩了 NFS 的坑"}
  ]
}'
```

Embedding 自动计算。返回 `{"status": "ok", "card_id": "01jz..."}`。

### 5. 后补 link

整理另一个 session 时发现和之前某张 card 有关联，可以独立补一条 link（需要显式指定 source 和 target）：

```
memory-talk link create '{
  "source_id": "<new-card-id>",
  "source_type": "card",
  "target_id": "<old-card-id>",
  "target_type": "card",
  "comment": "两个 session 都在讨论这个决策"
}'
```

### 6. 系统会自动把 session 标为 built

session 被一张 card 引用后（`links` 里带 `{type: "session", id: <session_id>}`），系统自动把 `unbuilt` tag 换成 `built`，不需要手动调。

## Quality Guidelines

- Card 要**自成一体** —— 单看 card 不读原始 session 也能理解。
- Summary 要**具体** —— "Decided X because Y"，不是 "Discussed options"。
- **宁少勿多**：一个 session 典型产出 2-5 张 card，而不是 20 张碎片 card。
- `rounds` 是记忆不是录像：冗余轮次直接跳过，不要硬塞。
- `thinking` 字段可选，只在保留关键推理时才加。

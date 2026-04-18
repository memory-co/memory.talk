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

- **挑 rounds**：寒暄、重复、确认 round 直接跳过；留下来的 round **逐字保留原始材料**（用户原话、代码全文、API 规格、错误日志），不要压成提纲。Talk-Card 中的 round 只有 `{role, text, thinking?}`，没有 `round_id / parent_id / content block` 这些 session 的原始结构——但 `text` 本身可以很长。详见下方 Quality Guidelines。
- **写 summary**：一句话捕捉核心结论、决策或洞察。这是 embedding 锚点，也是未来 recall 的关键。**"决定 X 因为 Y"** / **"发现 abm-worker 沙箱脚本共用骨架"** 远好过 **"讨论了数据库选项"** / **"创建了 fork_sandbox.py"**。
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

### 6. 标记 session 为已整理

整理完一个 session 的所有 card 之后，显式更新 tag：

```
memory-talk session tag <session_id> remove unbuilt
memory-talk session tag <session_id> add built
```

**没有自动机制** —— `built` / `unbuilt` 只是 Agent 用来追踪"这个 session 处理过没"的普通 tag，由你自己打、自己维护。下次 `/build` 靠 `--tag unbuilt` 过滤能不能工作，完全取决于你这一步有没有做。

## Quality Guidelines

- **Card 要自成一体** —— 单看 card 不读原始 session 也能理解。单卡预算约 **8192 token**，用得满才算写到位，不是"压到极简"的游戏。

- **Summary 写决策/洞察，不是流水账** —— "决定 X 因为 Y"、"发现 abm-worker 沙箱脚本共用骨架，基础设施改动要整批改" 好过 "创建了 fork_sandbox.py"。
  想一下：未来什么 query 会命中这条？命中后用户能立刻拿到什么结论？summary 必须答得上来。
  常见反模式 —— summary 把 rounds 再复述一遍（"做了 X、用了 Y、调了 Z"）：这只是在倒带，没抽出**为什么值得记住**。

- **Rounds 是记忆不是录像，但也不是提纲** —— 有分量的 round 要**逐字保留**原始材料：
  - 用户的原问题表述（而不是你的复述）
  - 写入/修改的代码全文（而不是"实现了 X 功能"这种摘要）
  - API 规格、错误日志、命令行输出、关键 diff
  - 决定性的推理链条
  寒暄/重复/确认轮直接跳过，但留下来的 round 不要压成一两句话。原文远比你复述的精准，8192 token 够用。

- **不要把"照抄式"session 当做无价值** —— 看似机械的任务里常藏着跨切面信息：继承的模式、吞下的技术债、未言明的惯例、为什么"一次就成"（通常因为有个骨架文件已经固化了所有跨切面问题）。这些才是未来 recall 的高价值锚点。先读完所有 round 再判断是否要建 card，别被"都是工具调用"的表象骗过去。

- **宁少勿多**：一个 session 典型 2–5 张 card，而不是 20 张碎片。

- **`thinking` 字段可选**，只在保留关键推理时加 —— "用户说 X 其实意思是 Y"、"选 A 不选 B 因为……"这种。

- **Card 无 update/delete**：写错了只能新建替代卡 + 等 TTL 淡忘，一段时间两三张并存、recall 噪音大。所以**第一次就要写到位** —— 读完 rounds 再动手，别急。

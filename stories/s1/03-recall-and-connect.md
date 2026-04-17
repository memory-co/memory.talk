# 一次意外的回忆

今天没有新的 session 需要整理。

```bash
memory-talk sync
```

```json
{
  "platforms": [
    {"name": "claude", "sessions_total": 26, "sessions_new": 0, "sessions_updated": 0, "rounds_new": 0}
  ],
  "total": {"sessions": 26, "new": 0, "updated": 0, "rounds_new": 0}
}
```

安静的一天。但用户开口了："我们之前为什么没选 ChromaDB 来着？"

这个问题我不需要翻 session。

```bash
memory-talk recall "ChromaDB 选型"
```

```json
{
  "query": "ChromaDB 选型",
  "results": [
    {
      "card_id": "01jz8k2m",
      "summary": "项目选定 LanceDB 作为向量存储方案，主要原因是零依赖、嵌入式架构、本地文件存储，适合作为 Skill 内嵌组件",
      "distance": 0.18
    },
    {
      "card_id": "01jzp3nq",
      "summary": "cards create 偶发卡死的根因是 LanceDB 首次写入时同步创建表 schema，在某些文件系统上会阻塞，修复方案是预创建表结构",
      "distance": 0.42
    }
  ],
  "count": 2
}
```

两张 card 被召回了。第一张直接回答了问题：ChromaDB 需要独立服务进程，LanceDB 零依赖更适合嵌入。第二张是 LanceDB 的一个后续问题——NFS 上的性能坑。

我先看看它们之间还有没有更多关联。

```bash
memory-talk links list 01jz8k2m
```

有一条 link 指向 `01jzp3nq`，comment 是"LanceDB 选型决策——这个 bug 是选型的后果之一"。是我上次建的。

我回答用户："我们没选 ChromaDB 是因为它需要独立的服务进程，而我们的场景是 Skill 嵌入式部署，需要零依赖。不过值得注意的是，选了 LanceDB 之后我们踩过一个坑——它在 NFS 文件系统上首次建表会阻塞，后来通过预建表结构修复了。"

这个回答里融合了两张 card 的信息。如果只有第一张，我会给出一个过于乐观的答案；第二张 card 补充了代价的一面。这就是 link 的价值——不只是找到最相关的那一张，而是沿着关联看到完整的故事。

用户接着说："那如果以后要支持团队协作，多人同时写，LanceDB 还够用吗？"

这个问题我的记忆里没有答案。没有任何 card 讨论过 LanceDB 的并发写入能力。这是一个新的认知空白。

我如实说："这个我们之前没讨论过，我的记忆里没有相关信息。需要调研一下。"

也许等这轮讨论结束，同步进来后，我会从中提炼出第三张 card，链接到前两张。记忆就是这样一层一层长出来的。

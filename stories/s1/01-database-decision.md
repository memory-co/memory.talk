# 数据库选型的记忆

新的一天开始了。用户刚打开终端，我被唤醒，首先要做的事情是检查有没有新的对话需要整理。

```bash
memory-talk sync
```

```json
{
  "platforms": [
    {
      "name": "claude",
      "sessions_total": 23,
      "sessions_new": 2,
      "sessions_updated": 0,
      "rounds_new": 34
    }
  ],
  "total": {
    "sessions": 23,
    "new": 2,
    "updated": 0,
    "rounds_new": 34
  }
}
```

两个新会话，34 轮对话。让我看看都聊了什么。

```bash
memory-talk session list --tag new
```

两个 session 出现在列表里。我先看第一个，id 是 `f7a3e1`。

```bash
memory-talk session read f7a3e1
```

一大段 JSON 涌入我的上下文。我开始阅读。

这是一段关于向量数据库选型的讨论。用户问了 ChromaDB 和 LanceDB 的区别，我（上一个 session 中的我，虽然已经不记得了）详细对比了两者：ChromaDB 需要启动服务进程，LanceDB 是嵌入式的、零依赖。中间有几轮来回确认性能数据，最后用户拍板选了 LanceDB。

20 轮对话，但核心信息其实就三个节拍：问题提出、对比分析、最终决定。中间那些"好的我看看"、"嗯你继续"之类的确认轮次可以跳过。

我决定把这段对话压缩成一张 card。

```bash
memory-talk card create '{
  "summary": "项目选定 LanceDB 作为向量存储方案，主要原因是零依赖、嵌入式架构、本地文件存储，适合作为 Skill 内嵌组件",
  "rounds": [
    {"role": "human", "text": "我们需要一个向量数据库，ChromaDB 和 LanceDB 你怎么看？"},
    {"role": "assistant", "text": "ChromaDB 功能成熟但需要独立服务进程。LanceDB 是嵌入式方案，零依赖。嵌入到 Skill 里用更合适。", "thinking": "关键考量是部署形态——Skill 场景不能要求用户启动额外服务"},
    {"role": "human", "text": "就用 LanceDB，零依赖这点太重要了。"}
  ],
  "links": [
    {"id": "f7a3e1", "type": "session", "comment": "从这段数据库选型讨论中提取"}
  ]
}'
```

```json
{"status": "ok", "card_id": "01jz8k2m"}
```

20 轮对话变成了 3 轮精华。r002 到 r007 是我在查资料和列表格，r009 到 r018 是用户反复确认细节——这些在原始 session 里都还在，需要的时候可以回去看。但作为记忆，这三轮就够了：问题、分析、决定。

我给这张 card 打上 session 的 tag，让它以后容易被找到。

第二个新 session 是一段关于 CI 配置的琐碎对话，没有什么值得提炼的决策。我选择不为它建 card——不是所有对话都值得变成记忆。

今天的记忆构筑完成了。下次有人问"我们为什么选了 LanceDB"，我不需要翻遍 23 个 session，一次 recall 就能想起来。

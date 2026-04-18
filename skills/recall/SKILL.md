---
name: recall
description: Use when needing to recall past conversations, decisions, or context from previous sessions
---

# Recall

三级递进检索：粗到细，只在需要时才下钻。每次访问自动刷新 TTL —— 常用的记忆不会被遗忘。

## Level 1: 向量检索

```
memory-talk recall "<query>" --top-k 5
```

返回语义最相关的 Talk-Card。每条结果带 `card_id / summary / session_id / ttl / distance / links[]`。**大多数查询到这一层就够了。**

Query 要具体："LanceDB vs ChromaDB 决策" 比 "数据库" 好。

命中会刷新 card 的 TTL（按 `ttl.card.factor`）—— 常被访问的 card 寿命会拉长。

### 2. 沿 link 扩展

如果返回的 card 指向相关但缺失的上下文，沿 link 追下去：

```
memory-talk card get <target_card_id> --link-id <link_id>
```

`--link-id` 传入的是上一级 recall / card get 返回的 `links[].link_id`。**传这个参数会刷新 link 自己的 TTL**（按 `ttl.link.factor`）—— 被反复走的连接不会被遗忘，冷门连接自然淡忘。

想看一个 card 的所有 link：

```
memory-talk link list <card_id>
memory-talk link list <card_id> --type card      # 只看连到其他 card 的
memory-talk link list <card_id> --type session   # 只看连到 session 的
```

Link 的 `comment` 字段写的是为什么关联 —— 优先顺着 comment 语义明确相关的 link 走，别盲目扩展所有连接。

## Level 3: 回到原始 session

如果需要确切措辞、完整代码片段或详细错误日志（压缩 card 里丢失的细节），回去读原始 session：

```
memory-talk session read <session_id> [--start N] [--end M]
```

Session 里的 round 是原始录像（带 `round_id / parent_id / timestamp / cwd / content block`），信息量大，按需取范围。

## Tips

- 读 card 时注意 `ttl` —— 数值小的说明很久没被访问，可能已经不再准确。
- 如果 recall 返回空或不相关，可能是该话题还没被整理成 card —— 提示用户跑 `/explore` + `/build`。
- 多条 card 命中时，要综合信息而不是只用第一条。summary 之间常常有互补。

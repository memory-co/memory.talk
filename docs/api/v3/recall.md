# Recall API

## POST /v3/recall

**无意识召回** —— harness hook 阶段被自动调用,把当前用户 prompt 喂进来,服务端立刻挑 top-K 最相关的 cards 以**极简形式**(只 `card_id` + `insight`)返回,供 hook 注入 LLM context。模拟"看到这条 prompt 时脑子里自动浮现的相关记忆"。

CLI 对应 [`recall`](../../cli/v3/recall.md) 命令。

跟 [`POST /v3/search`](search.md) 的差别(都是 AI 触发,差在意识形态):

| | `/v3/search` | `/v3/recall` |
|---|---|---|
| 触发 | AI 推理过程主动调 | harness hook 自动调 |
| 意识形态 | 有意识 / 决定要查 | 无意识 / 看到 prompt 即浮现 |
| `session_id` | 不需要 | **必填**(跨次召回去重 key) |
| 返回内容 | 完整(snippets / stats / source 等) | 极简(只 id + insight) |
| 命中桶 | cards + sessions | **只 cards**(session 太长不适合 inline 注入) |
| 去重 | 无 | 同 session 已召回过的 card 不再返回 |

### 请求体

```json
{
  "session_id": "sess_187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "prompt": "我想用 LanceDB 替换 Pinecone 怎么改",
  "top_k": 3
}
```

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `session_id` | 是 | — | **raw id**(平台原始 id 或带 `sess_` 前缀都接受),服务端规范化后用于去重 key |
| `prompt` | 是 | — | 用户当前的输入文本,作为检索 query |
| `top_k` | 否 | `3` | 召回上限。**默认极小**——hook 注入太多会稀释 prompt |

### session_id 命名空间

跟 `POST /v3/sessions` ingest 写入的 session_id **完全同源**(平台原始 id,例如 Claude Code 的 UUID)。recall 时该 session 大概率**还没被 sync 落库**(sync 是后端实时但仍有秒级延迟,recall 在 hook 阶段实时调)—— 所以 recall **不查 sessions 表、不报 404**;`session_id` 在 recall 路径里只起一个作用:**去重 key**。

等 watcher 跑完,这条 session 落库到同 id 下,recall 历史自然跟 session 挂钩。

### 响应

```json
{
  "session_id": "sess_187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "query": "我想用 LanceDB 替换 Pinecone 怎么改",
  "recalled": [
    {"card_id": "card_01jz8k2m", "insight": "选定 LanceDB 做向量存储"},
    {"card_id": "card_01jzp3nq", "insight": "异步数据库连接池实现"},
    {"card_id": "card_01jzq7rm", "insight": "搜索引擎核心原理"}
  ],
  "skipped_already_recalled": ["card_01jz9q3w"]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 回显规范化后的 session_id(带 `sess_` 前缀) |
| `query` | string | 回显 prompt |
| `recalled` | object[] | 本次**新返回**的 cards,按相关度排序;每项只有 `card_id` + `insight` |
| `skipped_already_recalled` | string[] | 本次检索原本会命中、但已在本 session 之前的 recall 里返回过 → 被去重过滤掉的 card_id 列表。供调试用 |

### 去重契约

同一 `session_id` 多次 recall 时,**已经返回过的 card 不会再返回**。这是 recall 的核心契约 —— hook 每轮 user prompt 都触发一次 recall,如果不去重会反复把同一批"老熟人"塞进 context。

机制(摘要):

- SQLite `recall_log` 表存 `(session_id, card_id, recalled_at)` 三元组;查询时 `LEFT JOIN` 排除已有
- 换一个新的 `session_id` 即可"忘掉"去重历史

### 副作用

- 写一条 `recall_log` 记录(用于去重)。**SQLite-only**,不落 file-layer:recall 是会话级瞬态状态,session 结束后无意义,丢了重新召回一次也无害
- **对每条本次新返回的 card 累加 `card.stats.recall_count += 1`** —— 论坛动力学里"被路过"的典型形态(自动召回 ≠ 主动 read,所以走单独计数器,不并入 `read_count`)。**`skipped_already_recalled` 跳掉的不动 stats**
- **不发任何 events**(recall 不是 lifecycle 状态变更,只是临时召回快照)
- **不落 `search_log`** —— recall / search 是两条概念路径

### 错误

| 情况 | 状态 |
|---|---|
| `session_id` 缺失 / 非字符串 | 400, `session_id required` |
| `prompt` 缺失 | 400, `prompt required` |
| `top_k` 超出 [1, 50] | 400, `top_k out of range` |
| 内部 vector / sqlite 异常 | 500 |

**没有 404** —— 即便 session 在 sessions 表里查不到,recall 也照跑(去重 key 在 recall_log 里独立成立,不依赖 sessions 表)。

### 跟 search 的设计对照

| | search | recall |
|---|---|---|
| 响应大小 | 完整 stats / snippets / source_cards 引用 | 只 card_id + insight |
| 排序公式 | `ranking_formula`(沉浮) | `relevance` 直接(已经在 prompt 语境里,不需要再叠论坛信号) |
| 跟 `card.stats` 关系 | 不修改 | `recall_count += 1` |
| 落 search_log? | 是 | 否 |

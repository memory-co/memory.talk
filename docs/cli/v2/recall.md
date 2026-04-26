# recall

**无意识召回** —— 在 harness hook 阶段被自动调用,把当前用户 prompt 喂进来,服务端立刻挑 top-K 最相关的 cards,以**极简**形式输出供 hook 注入到 LLM context。模拟"看到这条 prompt 时,脑子里自动浮现的相关记忆"。

跟 [search](search.md) 的差别(都是 AI 触发,差在意识形态):

| | `search` | `recall` |
|---|---|---|
| 触发 | AI 推理过程主动调用 | harness hook 自动调用 |
| 意识形态 | 有意识 / 决定要查 | 无意识 / 看到 prompt 即浮现 |
| session_id | 可选(只为审计) | **必填**(用于跨次召回去重) |
| 返回内容 | 完整(snippets / links / tags / source 等) | 极简(只 id + summary) |
| 命中桶 | cards + sessions | **只 cards**(原始 session 太长不适合 inline 注入) |
| TTL 续命 | 不续命 | 不续命 |
| 去重 | 无 | 同一 session_id 已经召回过的卡**不再返回** |

```bash
memory-talk recall <session_id> <prompt> [--top-k N] [--data-root PATH] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `<session_id>` | — | 必填。**raw id**,服务端会自动加 `sess_` 前缀。命名空间跟 [sync](sync.md) 完全一致(同一个平台 session 在 recall / sync 里是同一个 id)。 |
| `<prompt>` | — | 必填。用户当前的输入文本,作为检索 query。位置参数,长 prompt 在 shell 里需要正确引号转义。 |
| `--top-k` | 3 | 召回上限。`recall` 默认极小,因为它要的是"扫一眼脑海" —— top-3 已经够;hook 注入太多反而稀释 prompt。 |
| `--json` | 关 | 输出 JSON 而非默认 Markdown。 |

## session_id 命名空间

recall 接受的 session_id 跟 [sync](sync.md) 后写入 v2 的 session_id **完全一致**(都是平台原始 id,例如 Claude Code 的 UUID `187c6576-875f-4e3e-8fd8-f21fe60190b0`)。两个时间窗:

```
[recall 1]  hook → recall(sess_uuid, prompt_1)        ← session 还没被 sync 走
[recall 2]  hook → recall(sess_uuid, prompt_2)        ← 还没
[recall 3]  hook → recall(sess_uuid, prompt_3)        ← 还没
[sync]      定时器 → sync                             ← 现在才把这条 session 写进 v2
```

- recall 时,**v2 里这个 session 大概率还不存在**(sync 是异步定时的,recall 是 hook 实时的)。
- 所以 recall 不要求 session 在 v2 里存在,**不查 `db.sessions.get()`、不报 404**。session_id 在 recall 路径里只起一个作用:**去重 key**。
- 等 sync 跑完,这条 session 落地到 v2 的同 id 下,recall 历史也就跟 session 自然挂钩了。

## Markdown(默认)

````markdown
## Memory recall (3)

- `card_lancedb` · 选定 LanceDB 做向量存储
- `card_async_db_pool` · 异步数据库连接池实现
- `card_search_engine` · 搜索引擎核心原理
````

约定:
- 单条命中一行,只有 `\`<card_id>\` · <summary>`,没有 snippet、score、links、tags。极简到能直接 inline 进 prompt context 而不显得突兀。
- 命中数 0(本次没相关 card,或全被去重过滤掉了)→ **整段不输出**(stdout 空字符串)。harness 拿到空就当本次没召回,不打"无结果"占位文字干扰 prompt。
- TTY 渲染下这一段会变成有缩进的 list,管道里就是 raw 上面这种。

## JSON(`--json`)

```json
{
  "session_id": "sess_187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "query": "我想用 LanceDB 替换 Pinecone 怎么改",
  "recalled": [
    {"card_id": "card_lancedb", "summary": "选定 LanceDB 做向量存储"},
    {"card_id": "card_async_db_pool", "summary": "异步数据库连接池实现"},
    {"card_id": "card_search_engine", "summary": "搜索引擎核心原理"}
  ],
  "skipped_already_recalled": ["card_pinecone"]
}
```

字段:
- `recalled`:本次新返回的 cards,按相关度排序。`card_id` 带前缀,`summary` 是 card 的标题。**不含其它字段**(没有 score、snippets、links、tags、source、created_at) —— 极简就是契约。
- `skipped_already_recalled`:本次检索原本会命中、但**已经在本 session 之前的 recall 里返回过**因此被去重过滤掉的 card_id。供调试用,Markdown 视图不出。

## 去重(forward reference)

同一个 `session_id` 多次 recall 时,**已经返回过的 card 不会再返回**。这是 recall 的核心契约 —— hook 每轮 user prompt 都会触发一次 recall,如果不去重,会反复把同一批"老熟人记忆"塞进 context。

去重的具体机制(类似搜索引擎里 SEO 优化场景的 task / 去重队列模型)单独设计,本文档**不展开**。本文档只规定接口契约:

- 接口层面:`recall` 是幂等 of "新增召回",同一 (session_id, card_id) 不会出现两次。
- 撤销 / 重置:换一个新的 `session_id` 即可"忘掉"之前的去重历史。

## hook 集成姿势

```bash
# pseudo-code: harness 在 user 发出 prompt 之后、LLM 看到 prompt 之前
recall_md=$(memory-talk recall "$SESSION_ID" "$USER_PROMPT")
if [ -n "$recall_md" ]; then
  CONTEXT="${CONTEXT}

${recall_md}"
fi
# 然后把 CONTEXT 喂给 LLM
```

- 失败 / 超时 → recall 命令返回非零 exit,harness 应**忽略错误,继续不带召回的 prompt**(召回失败不该阻塞主流程)。
- recall 默认 timeout 短(秒级)避免拖慢 hook;调用方也可以包一层超时控制。

## 错误

| 情况 | Markdown(到 stderr) | JSON | exit |
|---|---|---|---|
| 缺 `<session_id>` 或 `<prompt>` | Click 阶段拦截 | 同 | 2 |
| `top_k` 超出范围 | `**error:** top_k out of range` | `{"error":"top_k out of range"}` | 1 |
| server 处于 `rebuilding` 状态 | `**error:** rebuilding` | `{"error":"rebuilding"}` | 1 |
| DSL 不适用(recall 不接受 `--where`) | — | — | — |

## 副作用

- 写一条 `recall_log` 记录(用于后续去重)。**SQLite-only**,不落 file-layer:recall 是会话级的瞬态状态,session 结束后无意义,丢了重新召回一次也无害。`/v2/rebuild` 会清空 recall_log,接受这个权衡。
- **不发任何 events**(recall 不是状态变更,只是临时召回快照)。
- **不刷新 cards / links 的 TTL**:recall 是 hook 自动触发,不代表 AI 真正用了这条记忆。续命会污染 TTL 信号("被自动召回 ≠ 被人主动用过")。要续命请走 [view](view.md)。
- **不落 `search_log`**:recall 跟 search 是两条概念路径,`search_log` 只记 search 的审计;recall 自己写 `recall_log`。

## 跟 sync 的关系

时间线、命名空间、生命周期参见上面 "session_id 命名空间" 一节。一句话总结:

> **recall 是给"还没成为正式记忆"的 in-flight 会话用的**。它跑在 sync 前面、用同一个 session_id,等 sync 把这条 session 真正写进 v2,recall 历史就跟这条 session 永久绑定了。

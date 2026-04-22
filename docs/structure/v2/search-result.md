# Search

v2 设计中心是 search——所有读取都从一次 search 起步。这份文档描述 search 的**输出形态**和服务端对 search 调用的**审计记录**（`search_log`）。

## ID 前缀约定（v2 通用）

v2 不再发行"追踪 token"（曾用的 `result_id` 已下线）。所有对外出现的主键都是**带前缀的裸 id**，前缀即类型：

| 对象 | 前缀 | 示例 |
|------|------|------|
| Card | `card_` | `card_01jz8k2m0000000000000000` |
| Session | `sess_` | `sess_187c6576_875f_4e3e_8fd8` |
| Link | `link_` | `link_01jzq7rm0000000000000000` |

**为什么不需要 result_id**：AI agent 调 tool 的整段对话本身就是 tool-use 记录，sync 之后可以完整复原"这次会话用了哪些 card / session"。服务端再造一层 result_id 是重复记账。

**为什么需要前缀**：`view <id>` 要能零成本判断读 card 还是 session，前缀一眼区分。服务端仍然会做存在性校验，但不靠前缀；前缀只是 UX。

## Search 输入

```json
{
  "query": "LanceDB 选型",
  "where": "tag = \"decision\" AND source = \"claude-code\"",
  "top_k": 10
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `query` | 是 | 检索文本；可空字符串（配合 `where` 做纯元数据过滤） |
| `where` | 否 | 元数据 DSL（字段：`session_id` / `card_id` / `tag` / `source` / `created_at`；运算符：`=` / `!=` / `LIKE` / `IN` / `NOT IN` / `AND`） |
| `top_k` | 否 | 每支（cards / sessions）上限，默认 `settings.search.default_top_k` |

## Search 输出

```json
{
  "search_id": "sch_01K7XABCDEFGHIJK01234",
  "query": "LanceDB 选型",
  "cards": {
    "count": 2,
    "results": [
      {
        "card_id": "card_01jz8k2m0000000000000000",
        "rank": 1,
        "score": 0.0312,
        "summary": "选定 LanceDB 做向量存储",
        "snippets": ["...**LanceDB**..."],
        "links": [
          {"link_id": "link_01jzq7rm0000000000000000", "target_id": "sess_f7a3e1", "target_type": "session", "comment": null, "ttl": 0},
          {"link_id": "link_01jzq8sn0000000000000000", "target_id": "card_01jzp3nq0000000000000000", "target_type": "card", "comment": "选型后果", "ttl": 1814400}
        ]
      }
    ]
  },
  "sessions": {
    "count": 1,
    "results": [
      {
        "session_id": "sess_187c6576_875f",
        "rank": 1,
        "score": 0.0289,
        "source": "claude-code",
        "tags": ["decision"],
        "snippets": ["...讨论 **LanceDB** 零依赖..."],
        "links": [
          {"link_id": "link_01jzq9tm0000000000000000", "target_id": "card_01jz8k2m0000000000000000", "target_type": "card", "comment": "从此对话提取", "ttl": 0}
        ]
      }
    ]
  }
}
```

要点：

- 响应直接返回**裸（前缀化）id**：`card_id` / `session_id` / `link_id` / `target_id`。拿到之后 `view` / `log` / `tag` / `link create` 都可以直接用。
- `search_id` 是本次 search 的审计 id（见下方 SearchLog），**不用于后续读取**——它只在服务端日志和 `/v2/log` 的 detail 里出现，用于把"这次 search 跟这个对象的 lifecycle 事件关联起来"。
- `links` 过滤掉已过期用户 link（`ttl < 0`）——只保留 `ttl >= 0`。想看过期 link 要走 `view`。

## SearchLog（服务端审计）

每次 `POST /v2/search` 在服务端追加一行——**记录完整的呈现给使用者的结果**，包含 snippets / score / summary / tags / links 等一切响应体内容。用意是：日后审计或追溯时能**完整复原"当时看到了什么"**，不用担心索引或数据改了以后再查对不上。

```json
{
  "search_id": "sch_01K7XABCDEFGHIJK01234",
  "query": "LanceDB 选型",
  "where": "tag = \"decision\" AND source = \"claude-code\"",
  "top_k": 10,
  "created_at": "2026-04-20T14:30:00Z",
  "cards": {
    "count": 2,
    "results": [
      {
        "card_id": "card_01jz8k2m",
        "rank": 1,
        "score": 0.0312,
        "summary": "选定 LanceDB 做向量存储",
        "snippets": ["...**LanceDB**..."],
        "links": [
          {"link_id": "link_01jzq7rm", "target_id": "sess_f7a3e1", "target_type": "session", "comment": null, "ttl": 0},
          {"link_id": "link_01jzq8sn", "target_id": "card_01jzp3nq", "target_type": "card", "comment": "选型后果", "ttl": 1814400}
        ]
      }
    ]
  },
  "sessions": {
    "count": 1,
    "results": [
      {
        "session_id": "sess_187c6576",
        "rank": 1,
        "score": 0.0289,
        "source": "claude-code",
        "tags": ["decision"],
        "snippets": ["...讨论 **LanceDB** 零依赖..."],
        "links": [
          {"link_id": "link_01jzq9tm", "target_id": "card_01jz8k2m", "target_type": "card", "comment": "从此对话提取", "ttl": 0}
        ]
      }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `search_id` | string | `sch_<ULID>`，本次 search 的唯一标识 |
| `query` | string | 检索文本（可空） |
| `where` | string \| null | 元数据 DSL 串（无则 null） |
| `top_k` | integer | 本次请求的 top_k |
| `created_at` | string | ISO 8601 |
| `cards` / `sessions` | object | 本次返回给调用方的完整两支结果。每个结果条目的字段与 [search 响应](../../cli/v2/search.md#输出) **一字不差**——含 `rank` / `score` / `summary` / `snippets` / `links` / `tags` 等 |

**为什么存完整响应**：
- `snippets` 由 FTS 在检索时动态生成、依赖当时的文档内容。如果只存 hit ids 而 session 之后被 `sync` 追加了新 round，事后查 log 时再重算 snippets 可能产生不同结果——存下来 snippet 原件才能真正复原"当时呈现给用户的那条摘要"。
- `score` 同理，依赖模型、向量库状态和 top_k，事后无法保证复现。
- `links` / `tags` 会随时间演化（link 过期、tag 增删），存快照才能看到"当时这张 card 旁边挂的是哪些关联、TTL 剩多少"。

**落库**：
- SQLite `search_log` 表（`cards` / `sessions` 列用 JSON 类型存整个 JSON blob）
- `~/.memory-talk/logs/search.jsonl`（每行一个完整的 SearchLog 对象）

SearchLog 不参与任何读取路径的验证——没有"凭据是否还活着"这种校验。它纯粹是审计/分析用：
- 看这台机器最近查什么、看到了什么
- 复原"这次 search 的用户呈现"——即便事后对象被改了也能追
- 统计 query 质量、snippet 触发率、link 命中率
- rebuild 时从 jsonl 重放回 SQLite

**没有 TTL**——search 的审计记录永久保留（或按 `settings.search.search_log_retention_days` 老化，如果配置了）。它不是"授权凭据"，不需要过期。

## 和其它结构的关系

- [`Talk-Card`](talk-card.md) 的 `links[].target_id` + `target_type` 直接暴露对端的前缀化 id，可直接喂给 `view`。
- [`Link`](link.md) 的 `link_id` / `source_id` / `target_id` 都是前缀化裸 id。
- [`Session`](session.md) 的 `index` 是 session 内 round 的稳定编号，`card` 写入时引用 round 的键——与任何外层 id 体系无关。
- [`Settings`](settings.md) 里**不再有** `search.result_ttl`——result_id 下线后该字段无意义。

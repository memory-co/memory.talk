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

每次 `POST /v2/search` 在服务端追加一行。

```json
{
  "search_id": "sch_01K7XABCDEFGHIJK01234",
  "query": "LanceDB 选型",
  "where": "tag = \"decision\" AND source = \"claude-code\"",
  "top_k": 10,
  "created_at": "2026-04-20T14:30:00Z",
  "card_hits": ["card_01jz8k2m...", "card_01jzp3nq..."],
  "session_hits": ["sess_187c6576..."]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `search_id` | string | `sch_<ULID>`，本次 search 的唯一标识 |
| `query` | string | 检索文本（可空） |
| `where` | string \| null | 元数据 DSL 串（无则 null） |
| `top_k` | integer | 本次请求的 top_k |
| `created_at` | string | ISO 8601 |
| `card_hits` | string[] | 本次命中的 card_id 列表（按 rank 排序） |
| `session_hits` | string[] | 本次命中的 session_id 列表（按 rank 排序） |

**落库**：
- SQLite `search_log` 表
- `~/.memory-talk/logs/search.jsonl`（append-only）

SearchLog 不参与任何读取路径的验证——没有"result_id 是否还活着"这种校验。它纯粹是审计/分析用：
- 看这台机器最近查什么
- 统计 query 和 hits 的关联
- rebuild 时从 jsonl 重放回 SQLite

**没有 TTL**——search 的原始查询记录永久保留（或按 `settings.search.search_log_retention_days` 老化，如果配置了）。它不是"授权凭据"，不需要过期。

## 和其它结构的关系

- [`Talk-Card`](talk-card.md) 的 `links[].target_id` + `target_type` 直接暴露对端的前缀化 id，可直接喂给 `view`。
- [`Link`](link.md) 的 `link_id` / `source_id` / `target_id` 都是前缀化裸 id。
- [`Session`](session.md) 的 `index` 是 session 内 round 的稳定编号，`card` 写入时引用 round 的键——与任何外层 id 体系无关。
- [`Settings`](settings.md) 里**不再有** `search.result_ttl`——result_id 下线后该字段无意义。

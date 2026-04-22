# Search API

## POST /v2/search

v2 主检索入口。hybrid FTS + 向量检索 + 元数据 DSL 过滤，返回两支结果（`cards` 和 `sessions`），命中条目直接带**带前缀的裸 id**（`card_<ULID>` / `sess_<ULID>`），拿到就能喂给 `/v2/view` / `/v2/log` / `/v2/links` / `/v2/tags/add`。

请求体：

```json
{
  "query": "LanceDB 选型",
  "where": "tag = \"decision\" AND source = \"claude-code\"",
  "top_k": 10
}
```

| 字段 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `query` | 是 | — | 检索文本。可为空字符串（配合 `where` 做纯元数据过滤） |
| `where` | 否 | 无 | 元数据过滤 DSL。支持字段：`session_id`、`card_id`、`tag`、`source`、`created_at`。运算符：`=`、`!=`、`LIKE`、`IN`、`NOT IN`、`AND` |
| `top_k` | 否 | `settings.search.default_top_k`（默认 10） | 每支（cards / sessions）上限 |

响应：

```json
{
  "search_id": "sch_01K7XABC...",
  "query": "LanceDB 选型",
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

## 返回体规则

- `card_id` / `session_id` / `link_id` / `target_id` 都是**带前缀的裸 id**，直接喂给 `/v2/view` / `/v2/log` / `/v2/links` 即可，无需转换。
- `search_id` 只是本次 search 的**审计 id**，出现在服务端 `search_log` 表和 `log` 命令的 `from_search_id` detail 里。**不参与任何后续读取的校验**——调用方留着或丢弃都行。
- `links` **过滤掉已过期的用户 link**（`ttl < 0`）——只出现 `ttl >= 0`（默认 link `ttl = 0` + 活跃用户 link `ttl > 0`）。想看过期 link 走 `/v2/view`。
- search 本身**不续命**任何对象或 link。

## 副作用

在服务端 `search_log` 表 + `logs/search/<UTC 日期>.jsonl` 追加一条，**存的是完整的响应体**——请求字段（`search_id` / `query` / `where` / `top_k` / `created_at`）和返回给调用方的全部结果（`cards` / `sessions` 两支，含 `snippets` / `score` / `summary` / `tags` / `links` 等）。用意是事后审计能复原"当时呈现给使用者的完整画面"，哪怕后续索引或对象被改也对得回。

详见 [../../structure/v2/search-result.md](../../structure/v2/search-result.md) 的 SearchLog 章节。

纯审计——不做"凭据发行"，不参与任何后续调用的校验。

## 错误

| 情况 | 状态 |
|------|------|
| `where` DSL 解析失败 | 400，`DSL parse error: <details>` |
| `top_k` 超过服务端上限 | 400 |

search 输入 / 输出 / 落库结构的完整定义见 [../../structure/v2/search-result.md](../../structure/v2/search-result.md)。
